export async function onRequestPost(context) {
  const { request, env } = context;

  try {
    const data = await request.json().catch(() => ({}));
    const { sessionId, userId, eventType = 'ping', metadata = {} } = data;

    if (!sessionId) {
      return new Response(JSON.stringify({ error: 'sessionId is required' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const ipAddress = request.headers.get('cf-connecting-ip') || 'unknown';
    const userAgent = request.headers.get('user-agent') || 'unknown';

    // Insert into PULSE_DB
    const statement = env.PULSE_DB.prepare(
      `INSERT INTO pulse_events (session_id, user_id, event_type, metadata, ip_address, user_agent)
       VALUES (?, ?, ?, ?, ?, ?)`
    );

    await statement.bind(
      sessionId,
      userId || null,
      eventType,
      JSON.stringify(metadata),
      ipAddress,
      userAgent
    ).run();

    return new Response(JSON.stringify({ success: true, message: 'Pulse recorded' }), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
      },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: err.message }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

export async function onRequestGet(context) {
  const { env } = context;

  try {
    // Retrieve latest 50 pulse logs
    const { results } = await env.PULSE_DB.prepare(
      `SELECT id, session_id, user_id, event_type, metadata, created_at 
       FROM pulse_events 
       ORDER BY id DESC LIMIT 50`
    ).all();

    // Get total count
    const countResult = await env.PULSE_DB.prepare(
      `SELECT COUNT(*) as total FROM pulse_events`
    ).first();

    return new Response(
      JSON.stringify({
        total_pulses: countResult ? countResult.total : 0,
        recent_pulses: results,
      }),
      {
        status: 200,
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': '*',
        },
      }
    );
  } catch (err) {
    return new Response(JSON.stringify({ error: err.message }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

// OPTIONS handler for CORS preflight
export async function onRequestOptions() {
  return new Response(null, {
    status: 204,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    },
  });
}
