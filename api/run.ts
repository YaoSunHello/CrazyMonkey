/* Starting a real run from the deployed console.
   ---------------------------------------------------------------------------
   A Vercel Function cannot host this pipeline, and the reason is not the one
   everybody guesses. Not size — Python functions get 500MB and the dependency
   set is 275MB. Not really duration either. It is that **a function's
   filesystem is read-only apart from /tmp**, and the agent loop writes
   `outputs/runs/` on every attempt.

   A Vercel Sandbox has none of those limits: a real Linux microVM, root, a
   writable disk, full network egress, and 45 minutes per session on Hobby
   against a run that takes 154-415 seconds per document. So the sandbox runs
   `python -m app.cli agent` exactly as it runs locally — the loop, the
   verifier, litellm and Daytona all untouched. Nothing about the pipeline
   changes to be deployed, which was the whole requirement.

   This function is only the control plane and the pipe: it starts the sandbox,
   then streams the CLI's own stderr back as server-sent events. The console
   already knows how to render those lines — it is the same terminal renderer
   the local launcher polls.

   The sandbox outlives the function that created it. That matters on Hobby,
   where this function is cut off at 300 seconds while the run is still going:
   the run does not die with it, and the browser reconnects with ?sandbox=<id>
   to pick the logs back up.  */

// Imported inside the handler, not here. At module scope a packaging problem —
// the dependency not installed, the wrong Node version — becomes an opaque
// FUNCTION_INVOCATION_FAILED with nothing to go on from outside. Imported late
// and caught, the same problem arrives as a sentence naming the module.
export const maxDuration = 300;

// Cloned rather than bundled. The pipeline is not part of this deployment and
// must not be — it is a Python project with its own lockfile, and `uv sync`
// inside the sandbox is the same install the repository gets anywhere else.
// The public fork, so no git credentials are needed for a public clone.
const REPO = "https://github.com/dimknaf/CrazyMonkey.git";

const ACCOUNT = /^[A-Za-z0-9_]{1,32}$/;
const PROFILE = /^[a-z0-9-]{1,64}$/;
const ALL = "__all__";

/* Only what the pipeline actually reads. Passing the whole environment into a
   sandbox would hand it this deployment's own credentials as well. */
const PASSED = [
  "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_USER_AGENT", "LLM_THINKING",
  "DAYTONA_API_KEY", "DAYTONA_TARGET",
  "AGENT_MAX_ATTEMPTS", "AGENT_MAX_TURNS", "AGENT_TIMEOUT",
];

function environment(): Record<string, string> {
  const out: Record<string, string> = { PYTHONUNBUFFERED: "1", NO_COLOR: "1" };
  for (const key of PASSED) {
    const value = process.env[key];
    if (value) out[key] = value;
  }
  return out;
}

export default async function handler(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const account = url.searchParams.get("account") || ALL;
  const profile = url.searchParams.get("profile") || "journal-entries";

  if (account !== ALL && !ACCOUNT.test(account)) {
    return Response.json({ error: `not an account code: ${account}` }, { status: 400 });
  }
  if (!PROFILE.test(profile)) {
    return Response.json({ error: `not a profile id: ${profile}` }, { status: 400 });
  }

  /* Said before anything is created, because a missing key here fails deep
     inside the run with a message about the model endpoint, minutes later. */
  const missing = ["LLM_BASE_URL", "LLM_API_KEY"].filter((k) => !process.env[k]);
  if (missing.length) {
    return Response.json(
      {
        error: `this deployment has no ${missing.join(" or ")}`,
        fix: "Vercel → Project → Settings → Environment Variables, then redeploy",
      },
      { status: 503 },
    );
  }

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const send = (line: string) =>
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(line)}\n\n`));

      try {
        const { Sandbox } = await import("@vercel/sandbox");
        send("creating a sandbox…");
        const sandbox = await Sandbox.create({
          source: { type: "git", url: REPO, revision: "main", depth: 1 },
          resources: { vcpus: 2 },
          timeout: 45 * 60 * 1000,
          runtime: "python3.13",
        });
        send(`sandbox ${sandbox.sandboxId} up — installing dependencies`);

        // uv is on the managed Python image, but which image a runtime maps to
        // is not something to bet a demo on — installing it when it is already
        // there costs a second, and not having it is a dead run.
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
          for (const line of (await install.stderr()).split("\n").slice(-25)) {
            if (line.trim()) send(line);
          }
          return;
        }
        send("dependencies installed");

        const args = ["run", "python", "-m", "app.cli", "agent"];
        args.push(...(account === ALL
          ? ["--all", "--parallel", "4"]
          : ["--account", account]));
        args.push("--profile", profile);
        send(`$ uv ${args.join(" ")}`);

        // Detached, so the run belongs to the sandbox rather than to this
        // request. If the function is cut off at its deadline, the run carries
        // on and the logs can be re-attached.
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
        send(`__error__ ${error instanceof Error ? error.message : String(error)}`);
      } finally {
        controller.close();
        // Left running deliberately: it holds outputs/runs/ for the next call
        // to collect, and it expires on its own timeout.
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
