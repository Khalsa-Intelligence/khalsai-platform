export async function onRequestGet({ env }) {
  const { results } = await env.DB.prepare(
    "SELECT username, score, created_at FROM leaderboard ORDER BY score DESC LIMIT 50"
  ).all();

  return Response.json(results);
}

export async function onRequestPost({ request, env }) {
  const { username, score } = await request.json();

  if (!username || typeof score !== 'number') {
    return new Response('Invalid payload', { status: 400 });
  }

  await env.DB.prepare(
    "INSERT INTO leaderboard (username, score) VALUES (?, ?)"
  ).bind(username, score).run();

  return Response.json({ success: true }, { status: 201 });
}
