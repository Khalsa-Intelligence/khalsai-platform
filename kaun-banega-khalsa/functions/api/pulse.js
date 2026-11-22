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

    if (eventType === 'compact_session') {
      if (!cleanEventCode) {
        return new Response(JSON.stringify({ error: 'eventCode is required for compaction' }), {
          status: 400,
          headers: {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
          },
        });
      }

      const { results } = await env.PULSE_DB.prepare(
        `SELECT id, user_id, event_type, metadata
         FROM pulse_events
         WHERE UPPER(REPLACE(event_code, '#', '')) = ?
           AND event_type IN ('quiz_answer', 'leaderboard_snapshot', 'leaderboard_reset')
         ORDER BY id ASC`
      )
        .bind(cleanEventCode)
        .all();

      const rows = results || [];
      let lastResetId = 0;
      const snapshotTotals = new Map();
      const awardedByUserQuiz = new Map();
      const idsToDelete = [];

      for (const r of rows) {
        const rId = Number(r.id) || 0;
        let meta = r.metadata;
        try {
          while (typeof meta === 'string') {
            meta = JSON.parse(meta.replace(/[\u2026]/g, '...'));
          }
        } catch (e) {
          meta = null;
        }

        if (r.event_type === 'leaderboard_reset') {
          lastResetId = rId;
          snapshotTotals.clear();
          awardedByUserQuiz.clear();
          continue;
        }

        if (rId <= lastResetId || !meta) {
          if (r.event_type === 'quiz_answer' || r.event_type === 'leaderboard_snapshot') {
            idsToDelete.push(rId);
          }
          continue;
        }

        if (r.event_type === 'leaderboard_snapshot') {
          const user = String(meta.userName || r.user_id || '').trim();
          const pts = Math.max(0, Number(meta.totalScore) || 0);
          if (user) {
            snapshotTotals.set(user, (snapshotTotals.get(user) || 0) + pts);
          }
          idsToDelete.push(rId);
        } else if (r.event_type === 'quiz_answer') {
          const user = String(meta.userName || r.user_id || '').trim();
          const quizId = String(meta.quizId ?? '').trim();
          const pts = Math.max(0, Number(meta.pointsEarned) || 0);
          if (user && quizId) {
            const key = `${user}::${quizId}`;
            if (!awardedByUserQuiz.has(key)) {
              awardedByUserQuiz.set(key, pts);
            }
          }
          idsToDelete.push(rId);
        }
      }

      const finalTotals = new Map(snapshotTotals);
      for (const [key, pts] of awardedByUserQuiz.entries()) {
        const sepIdx = key.indexOf('::');
        if (sepIdx > 0) {
          const user = key.slice(0, sepIdx);
          finalTotals.set(user, (finalTotals.get(user) || 0) + pts);
        }
      }

      const batchStatements = [];

      // 1. Insert 1 aggregated snapshot row per user FIRST
      for (const [user, totalScore] of finalTotals.entries()) {
        if (totalScore > 0) {
          batchStatements.push(
            env.PULSE_DB.prepare(
              `INSERT INTO pulse_events (session_id, user_id, event_type, event_code, metadata, ip_address, user_agent)
               VALUES (?, ?, 'leaderboard_snapshot', ?, ?, ?, ?)`
            ).bind(
              sessionId,
              user,
              cleanEventCode,
              JSON.stringify({
                userName: user,
                totalScore,
                eventCode: cleanEventCode,
                compactedAt: Date.now(),
              }),
              ipAddress,
              userAgent
            )
          );
        }
      }

      // 2. Delete superseded score rows & ephemeral noise ONLY (never quiz questions or Q&A)
      if (idsToDelete.length > 0) {
        const chunkSize = 80;
        for (let i = 0; i < idsToDelete.length; i += chunkSize) {
          const chunk = idsToDelete.slice(i, i + chunkSize);
          const placeholders = chunk.map(() => '?').join(',');
          batchStatements.push(
            env.PULSE_DB.prepare(
              `DELETE FROM pulse_events WHERE id IN (${placeholders})`
            ).bind(...chunk)
          );
        }
      }

      batchStatements.push(
        env.PULSE_DB.prepare(
          `DELETE FROM pulse_events
           WHERE UPPER(REPLACE(event_code, '#', '')) = ?
             AND event_type IN ('ping', 'reaction', 'quiz_release', 'quiz_clear', 'quiz_stop', 'spotlight_question')`
        ).bind(cleanEventCode)
      );

      if (batchStatements.length > 0) {
        await env.PULSE_DB.batch(batchStatements);
      }

      return new Response(
        JSON.stringify({
          success: true,
          message: 'Session compacted safely',
          usersCompacted: finalTotals.size,
          rowsRemoved: idsToDelete.length,
        }),
        {
          status: 200,
          headers: {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
          },
        }
      );
    }

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
  const PAGE_LIMIT = 1000;

  try {
    let query = `SELECT id, session_id, user_id, event_type, event_code, metadata, created_at
                 FROM pulse_events WHERE 1=1`;
    const params = [];

    if (seriesPrefix) {
      const cleanSeries = String(seriesPrefix).replace(/^#/, '').trim().toUpperCase();
      query += ` AND UPPER(REPLACE(event_code, '#', '')) LIKE ? AND event_type IN ('quiz_answer', 'leaderboard_snapshot', 'leaderboard_reset')`;
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

    query += ` ORDER BY id ASC LIMIT ${PAGE_LIMIT}`;

    const { results } = await env.PULSE_DB.prepare(query).bind(...params).all();
    const rows = results || [];

    return new Response(
      JSON.stringify({
        recent_pulses: rows,
        has_more: rows.length === PAGE_LIMIT,
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
