export async function onRequestPost(context) {
  const { request, env } = context;

  try {
    const data = await request.json().catch(() => ({}));
    const { sessionId, userId, eventType = 'ping', eventCode, metadata = {} } = data;

    if (!sessionId) {
      return new Response(JSON.stringify({ error: 'sessionId is required' }), {
        status: 400,
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': '*',
        },
      });
    }

    const ipAddress = request.headers.get('cf-connecting-ip') || 'unknown';
    const userAgent = request.headers.get('user-agent') || 'unknown';
    const cleanEventCode = eventCode ? String(eventCode).replace(/^#/, '').trim().toUpperCase() : null;

    await env.PULSE_DB.prepare(
      `INSERT INTO pulse_events (session_id, user_id, event_type, event_code, metadata, ip_address, user_agent)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    )
      .bind(
        sessionId,
        userId || null,
        eventType,
        cleanEventCode,
        JSON.stringify(metadata),
        ipAddress,
        userAgent
      )
      .run();

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
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
      },
    });
  }
}

export async function onRequestGet(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const eventCode = url.searchParams.get('eventCode');
  const seriesPrefix = url.searchParams.get('seriesPrefix');
  const afterIdRaw = url.searchParams.get('afterId');
  const afterId = afterIdRaw !== null ? Number(afterIdRaw) : 0;

  try {
    let query = `SELECT id, session_id, user_id, event_type, event_code, metadata, created_at
                 FROM pulse_events WHERE 1=1`;
    const params = [];

    if (seriesPrefix) {
      const cleanSeries = String(seriesPrefix).replace(/^#/, '').trim().toUpperCase();
      query += ` AND UPPER(REPLACE(event_code, '#', '')) LIKE ? AND event_type IN ('quiz_answer', 'leaderboard_reset')`;
      params.push(`${cleanSeries}%`);
    } else if (eventCode) {
      const cleanCode = String(eventCode).replace(/^#/, '').trim().toUpperCase();
      query += ` AND UPPER(REPLACE(event_code, '#', '')) = ?`;
      params.push(cleanCode);
    }

    if (!Number.isNaN(afterId) && afterId > 0) {
      query += ` AND id > ?`;
      params.push(afterId);
    }

    query += ` ORDER BY id ASC LIMIT 500`;

    const { results } = await env.PULSE_DB.prepare(query).bind(...params).all();

    return new Response(
      JSON.stringify({
        recent_pulses: results || [],
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
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
      },
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
