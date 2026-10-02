export async function onRequestPost(context) {
  const { request, env } = context;

  try {
    const data = await request.json().catch(() => ({}));
    const { sessionId, userId, eventType = 'ping', eventCode, metadata = {} } = data;

    if (!sessionId) {
      return new Response(JSON.stringify({ error: 'sessionId is required' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const ipAddress = request.headers.get('cf-connecting-ip') || 'unknown';
    const userAgent = request.headers.get('user-agent') || 'unknown';

    // Store event_code along with metadata
    const statement = env.PULSE_DB.prepare(
      `INSERT INTO pulse_events (session_id, user_id, event_type, event_code, metadata, ip_address, user_agent)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    );

    await statement.bind(
      sessionId,
      userId || null,
      eventType,
      eventCode || null,
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
  const { request, env } = context;
  const url = new URL(request.url);
  const eventCode = url.searchParams.get('eventCode');

  try {
    let query = `SELECT id, session_id, user_id, event_type, event_code, metadata, created_at 
                 FROM pulse_events`;
    let params = [];

    if (eventCode) {
      query += ` WHERE event_code = ?`;
      params.push(eventCode);
    }

    // Always sort by ID ASC so client replays events in chronological order
    query += ` ORDER BY id ASC LIMIT 100`;

    const { results } = await env.PULSE_DB.prepare(query).bind(...params).all();

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
