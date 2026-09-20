export async function onRequestPost(context) {
  const { request, env } = context;

  try {
    const { password } = await request.json();

    // Updated admin password
    const ADMIN_PASSWORD = env.ADMIN_PASSWORD || "6789";

    if (password !== ADMIN_PASSWORD) {
      return new Response(JSON.stringify({ error: "Unauthorized: Invalid Password" }), {
        status: 401,
        headers: { "Content-Type": "application/json" }
      });
    }

    const db = env.FEEDBACK_DB || env.DB;

    // Fetch all submissions ordered by newest first
    const { results } = await db.prepare(
      `SELECT * FROM sangaat_feedback ORDER BY created_at DESC`
    ).all();

    return new Response(JSON.stringify({ success: true, data: results }), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: err.message }), {
      status: 500,
      headers: { "Content-Type": "application/json" }
    });
  }
}
