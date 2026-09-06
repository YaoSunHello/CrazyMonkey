/* The smallest function that can exist, to tell two failures apart.
   /api/run returns FUNCTION_INVOCATION_FAILED, which is a crash at module load
   — before any of its own error handling. That is either something in that file
   or the way this project builds functions at all. This answers which. */
export default function handler(): Response {
  return Response.json({ ok: true, runtime: process.version });
}
