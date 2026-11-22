export async function onRequestGet({ env }) {
  const { results } = await env.DB.prepare(
    "SELECT id, name, age, level, score FROM leaderboard ORDER BY score DESC LIMIT 50"
  ).all();

  return Response.json(results);
}

export async function onRequestPost({ request, env }) {
  const payload = await request.json();
  const { id, name, username, age, level, score } = payload;

  // Support both 'name' or 'username' from the incoming request body
  const playerName = name || username;

  if (!playerName || typeof score !== 'number') {
    return new Response('Invalid payload', { status: 400 });
  }

  const recordId = id || Date.now();
  const playerAge = typeof age === 'number' ? age : null;
  const playerLevel = typeof level === 'number' ? level : null;

  await env.DB.prepare(
    "INSERT INTO leaderboard (id, name, age, level, score) VALUES (?, ?, ?, ?, ?)"
  ).bind(recordId, playerName, playerAge, playerLevel, score).run();

  return Response.json({ success: true }, { status: 201 });
}
