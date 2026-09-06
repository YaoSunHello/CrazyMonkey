/* Starting a real run from the deployed console.
   ---------------------------------------------------------------------------
   A Vercel Function cannot host this pipeline, and the reason is not the one
   everybody guesses. Not size — Python functions get 500MB and the dependency
   set is 275MB. Not really duration either. It is that **a function's
   filesystem is read-only apart from /tmp**, and the agent loop writes
   `outputs/runs/` on every attempt.

   A Vercel Sandbox has none of those limits: a real Linux microVM, root, a
   writable disk, full network egress, and 45 minutes per session against a run
   that takes 154-415 seconds per document. So the sandbox runs
   `python -m app.cli agent` exactly as a laptop runs it — the loop, the
   verifier, litellm and Daytona all untouched. Nothing about the pipeline
   changed in order to deploy it, which was the point.

   This file is only the control plane and the pipe.

   CommonJS with the (req, res) signature, deliberately. The first version was
   TypeScript exporting a Web-standard `Request -> Response` handler, and it
   returned FUNCTION_INVOCATION_FAILED on every call — a crash at module load,
   before any of its own error handling, with nothing readable from outside.
   Two probes settled it: the identical logic as plain CommonJS answered 200
   while the TypeScript one would not load at all. So this project builds one
   kind of function, and this is that kind.  */

const REPO = "https://github.com/dimknaf/CrazyMonkey.git";
const ACCOUNT = /^[A-Za-z0-9_]{1,32}$/;
const PROFILE = /^[a-z0-9-]{1,64}$/;
const ALL = "__all__";

/* Only what the pipeline reads. Handing a sandbox the whole environment would
   hand it this deployment's own credentials as well. */
const PASSED = [
  "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_USER_AGENT", "LLM_THINKING",
  "LLM_ENABLE_THINKING",
  "DAYTONA_API_KEY", "DAYTONA_TARGET",
  "AGENT_MAX_ATTEMPTS", "AGENT_MAX_TURNS", "AGENT_TIMEOUT",
];

function environment() {
  const out = { PYTHONUNBUFFERED: "1", NO_COLOR: "1" };
  for (const key of PASSED) {
    if (process.env[key]) out[key] = process.env[key];
  }
  return out;
}

// Stamped so a stale deployment can be told apart from a live one that is
// failing. Without it, "still 500" means either and there is no way to know.
const BUILD = "run.js/cjs-3-dynamic-import";

module.exports = async (req, res) => {
  const url = new URL(req.url, `https://${req.headers.host}`);
  const account = url.searchParams.get("account") || ALL;
  const profile = url.searchParams.get("profile") || "journal-entries";

  /* Answers before anything else can throw: which build is serving, whether
     the sandbox module resolves, and which of the pipeline's keys this
     deployment actually has. Names only — never a value. */
  if (url.searchParams.get("probe")) {
    let sandbox = "ok";
    try { await import("@vercel/sandbox"); } catch (error) { sandbox = String(error && error.message); }
    res.setHeader("Content-Type", "application/json");
    return res.end(JSON.stringify({
      build: BUILD,
      runtime: process.version,
      sandbox_module: sandbox,
      env_present: PASSED.filter((k) => process.env[k]),
      env_missing: PASSED.filter((k) => !process.env[k]),
    }, null, 1));
  }

  const reject = (code, payload) => {
    res.statusCode = code;
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify(payload));
  };

  if (account !== ALL && !ACCOUNT.test(account)) {
    return reject(400, { error: `not an account code: ${account}` });
  }
  if (!PROFILE.test(profile)) {
    return reject(400, { error: `not a profile id: ${profile}` });
  }

  /* Said before anything is created. Without this the run fails minutes later,
     deep inside the loop, with a message about the model endpoint. */
  const missing = ["LLM_BASE_URL", "LLM_API_KEY"].filter((k) => !process.env[k]);
  if (missing.length) {
    return reject(503, {
      error: `this deployment has no ${missing.join(" or ")}`,
      fix: "Vercel → Project → Settings → Environment Variables (Production), then redeploy",
      needed: PASSED,
    });
  }

  res.writeHead(200, {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache, no-transform",
    Connection: "keep-alive",
    "X-Accel-Buffering": "no",
  });

  const send = (line) => {
    try { res.write(`data: ${JSON.stringify(String(line))}\n\n`); } catch (_) { /* client gone */ }
  };

  try {
    // Dynamic import, not require: the package ships a .cjs build but that
    // build itself requires an ES-only module, so require() dies at the
    // first call with "require() of ES Module ... not supported". import()
    // works from CommonJS and is the only way in.
    const { Sandbox } = await import("@vercel/sandbox");

    send("creating a sandbox…");
    const sandbox = await Sandbox.create({
      source: { type: "git", url: REPO, revision: "main", depth: 1 },
      resources: { vcpus: 2 },
      timeout: 45 * 60 * 1000,
      runtime: "python3.13",
    });
    send(`sandbox ${sandbox.sandboxId} up — installing dependencies`);

    // uv is on the managed Python image, but which image a runtime maps to is
    // not documented tightly enough to bet a demo on. Installing it when it is
    // already there costs a second; not having it is a dead run.
    const install = await sandbox.runCommand({
      cmd: "sh",
      args: [
        "-c",
        "command -v uv >/dev/null 2>&1 || pip install --quiet uv; " +
        "uv sync --frozen 2>&1 || uv sync 2>&1",
      ],
      cwd: "/vercel/sandbox",
    });
    if (install.exitCode !== 0) {
      send(`installing dependencies failed (${install.exitCode})`);
      for (const line of String(await install.stderr()).split("\n").slice(-25)) {
        if (line.trim()) send(line);
      }
      send("__exit__ 1");
      return res.end();
    }
    send("dependencies installed");

    const args = ["run", "python", "-m", "app.cli", "agent"];
    args.push(...(account === ALL ? ["--all", "--parallel", "4"] : ["--account", account]));
    args.push("--profile", profile);
    send(`$ uv ${args.join(" ")}`);

    // Detached, so the run belongs to the sandbox and not to this request. A
    // function cut off at its deadline does not take the run down with it.
    const command = await sandbox.runCommand({
      cmd: "uv", args, cwd: "/vercel/sandbox/backend",
      env: environment(), detached: true,
    });

    for await (const log of command.logs()) {
      for (const line of String(log.data).split("\n")) {
        if (line.trim()) send(line);
      }
    }
    const done = await command.wait();
    send(`__exit__ ${done.exitCode}`);
  } catch (error) {
    send(`__error__ ${error && error.message ? error.message : String(error)}`);
  } finally {
    res.end();
  }
};
