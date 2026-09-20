export async function onRequestPost(context) {
  const { request, env } = context;

  // Always return CORS & JSON headers
  const headers = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*"
  };

  try {
    const body = await request.json();
    const { session_name, rating, learnt_new, touched_comment, encouragement_comment } = body;

    if (!session_name || !rating || !learnt_new) {
      return new Response(JSON.stringify({ error: "Missing required fields" }), { status: 400, headers });
    }

    // Access D1 database binding
    const db = env.FEEDBACK_DB || env.DB;

    if (!db) {
      return new Response(JSON.stringify({ error: "D1 database binding (FEEDBACK_DB) missing in Cloudflare" }), { status: 500, headers });
    }

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

    return new Response(JSON.stringify({ success: true }), { status: 200, headers });
  } catch (err) {
    return new Response(JSON.stringify({ error: err.message || "Internal Server Error" }), { status: 500, headers });
  }
}
