// The same question again, in plain CommonJS with the Node signature, in case
// the Web-standard handler or the TypeScript step is what this project cannot do.
module.exports = (req, res) => {
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify({ ok: true, style: "node-cjs", runtime: process.version }));
};
