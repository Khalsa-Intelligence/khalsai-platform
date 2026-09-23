export async function onRequestPost(context) {
  const { request, env } = context;

  const headers = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*"
  };

  try {
    const body = await request.json();
    const { id, password } = body;

    if (password !== "6789") {
      return new Response(
        JSON.stringify({ success: false, error: "Unauthorized: Invalid Password" }),
        { status: 401, headers }
      );
    }

    if (!id) {
      return new Response(
        JSON.stringify({ success: false, error: "Missing record ID" }),
        { status: 400, headers }
      );
    }

    const db = env.FEEDBACK_DB || env.DB;
    if (!db) {
      return new Response(
        JSON.stringify({ success: false, error: "Database binding missing" }),
        { status: 500, headers }
      );
    }

    await db.prepare("DELETE FROM sangaat_feedback WHERE id = ?").bind(id).run();

    return new Response(
      JSON.stringify({ success: true, message: "Feedback deleted successfully" }),
      { status: 200, headers }
    );
  } catch (err) {
    return new Response(
      JSON.stringify({ success: false, error: err.message || "Internal Server Error" }),
      { status: 500, headers }
    );
  }
}
