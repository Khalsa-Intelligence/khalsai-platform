export async function onRequestPost(context) {
  const { request, env } = context;

  try {
    const body = await request.json();
    const { session_name, rating, learnt_new, touched_comment, encouragement_comment } = body;

    if (!session_name || !rating || !learnt_new) {
      return new Response(JSON.stringify({ error: "Missing required fields" }), {
        status: 400,
        headers: { "Content-Type": "application/json" }
      });
    }

    // Accesses your Cloudflare D1 database binding
    const db = env.FEEDBACK_DB || env.DB;

    await db.prepare(
      `INSERT INTO sangaat_feedback (session_name, rating, learnt_new, touched_comment, encouragement_comment)
       VALUES (?, ?, ?, ?, ?)`
    ).bind(
      session_name,
      parseInt(rating),
      learnt_new,
      touched_comment || "",
      encouragement_comment || ""
    ).run();

    return new Response(JSON.stringify({ success: true }), {
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
