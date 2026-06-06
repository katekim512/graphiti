import html


def render_page(*, browser_url: str, saga_name: str, one_neo4j_query: str) -> str:
    page = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Graphiti Realtime KG Demo</title>
    <style>
      :root {
        --ink: #102a43;
        --muted: #52606d;
        --paper: #fbfaf7;
        --panel: #ffffff;
        --accent: #1f6feb;
        --accent2: #f0b429;
        --line: #d9e2ec;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: Georgia, serif;
        color: var(--ink);
        background:
          radial-gradient(circle at top left, #fff4d6 0, transparent 28%),
          radial-gradient(circle at bottom right, #d9f0ff 0, transparent 25%),
          var(--paper);
      }
      .shell {
        display: grid;
        grid-template-columns: 380px 1fr;
        min-height: 100vh;
      }
      .left, .right { padding: 24px; }
      .left {
        border-right: 1px solid var(--line);
        background: rgba(255,255,255,0.72);
        backdrop-filter: blur(10px);
      }
      h1 { margin: 0 0 8px; font-size: 32px; }
      p { margin: 0 0 16px; color: var(--muted); line-height: 1.5; }
      textarea {
        width: 100%;
        min-height: 110px;
        padding: 14px;
        border: 1px solid var(--line);
        border-radius: 14px;
        font: inherit;
        background: #fff;
      }
      button {
        border: 0;
        border-radius: 999px;
        padding: 12px 18px;
        margin-right: 8px;
        background: var(--accent);
        color: white;
        font: inherit;
        cursor: pointer;
      }
      button.secondary { background: #243b53; }
      .status, .panel {
        margin-top: 16px;
        padding: 14px 16px;
        border-radius: 16px;
        background: var(--panel);
        border: 1px solid var(--line);
      }
      .panel h2 {
        margin: 0 0 10px;
        font-size: 18px;
      }
      .facts, .episodes { font-size: 14px; line-height: 1.5; color: var(--muted); }
      .graph-wrap {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 20px;
        padding: 12px;
        overflow: auto;
      }
      .query-box {
        width: 100%;
        min-height: 120px;
        padding: 12px;
        border-radius: 14px;
        border: 1px solid var(--line);
        background: #fffdf8;
        color: var(--ink);
        font: 13px/1.5 Menlo, monospace;
        white-space: pre-wrap;
      }
      .neo-link {
        display: inline-block;
        margin-top: 10px;
        color: var(--accent);
        text-decoration: none;
        font-weight: 600;
      }
      @media (max-width: 920px) {
        .shell { grid-template-columns: 1fr; }
        .left { border-right: 0; border-bottom: 1px solid var(--line); }
      }
    </style>
  </head>
  <body>
    <div class="shell">
      <section class="left">
        <h1>Realtime KG Demo</h1>
        <p>사전 지식을 하나씩 추가하고, 이후 질문을 보내면 Graphiti KG를 바탕으로 답변과 근거 하이라이트를 같이 보여줍니다.</p>
        <div class="panel">
          <h2>Prior Knowledge</h2>
          <textarea id="knowledgeInput" placeholder="예: A Psalm for the Wild-Built는 hopeful하고 gentle한 slow burn SF야. dystopian한 분위기는 강하지 않아."></textarea>
          <div style="margin-top: 12px;">
            <button id="addKnowledgeBtn" class="secondary">Add Knowledge</button>
          </div>
        </div>
        <div class="panel">
          <h2>User Question</h2>
          <textarea id="chatInput" placeholder="예: 나는 감정선이 진한 SF를 좋아해. tone은 hopeful하고, pacing은 slow burn이면 좋겠어. dystopian한 책은 피하고 싶어. 비슷한 책 추천해줘."></textarea>
          <div style="margin-top: 12px;">
            <button id="sendBtn">Ask With KG</button>
            <button id="resetBtn" class="secondary">Reset Graph</button>
          </div>
        </div>
        <div id="status" class="status">Ready.</div>
        <div class="panel">
          <h2>Better Input Shape</h2>
          <div class="facts">
            <div>1. 사전 지식: 책/작품 특징을 명시적으로 한 줄씩 추가</div>
            <div>2. 질문: 선호 장르, 톤, 페이싱, 회피 요소를 분명하게 작성</div>
            <div>3. 질문 예시: "hopeful한 slow burn SF 추천해줘"</div>
          </div>
        </div>
        <div class="panel">
          <h2>Assistant Answer</h2>
          <div id="answerText" class="facts">No grounded answer yet.</div>
        </div>
        <div class="panel">
          <h2>Grounding</h2>
          <div id="groundingFacts" class="facts">No supporting KG slice selected yet.</div>
        </div>
        <div class="panel">
          <h2>Episodes</h2>
          <div id="episodes" class="episodes"></div>
        </div>
        <div class="panel">
          <h2>Relations</h2>
          <div id="relations" class="facts"></div>
        </div>
      </section>
      <section class="right">
        <div class="panel" style="margin-bottom: 16px;">
          <h2>Open Neo4j Browser</h2>
          <p>Neo4j와 완전히 같은 그래프 화면을 보려면 아래 Browser를 같이 열어두면 됩니다.</p>
          <a class="neo-link" href="__BROWSER_URL__" target="_blank" rel="noreferrer">Open Neo4j Browser</a>
        </div>
        <div class="panel" style="margin-bottom: 16px;">
          <h2>One Neo4j Query</h2>
          <div id="querySaga" class="query-box">__ONE_QUERY__</div>
        </div>
        <div class="graph-wrap">
          <div id="graphSvg">Loading...</div>
        </div>
        <div class="graph-wrap" style="margin-top: 16px;">
          <div id="groundedGraphSvg">Ask a question to highlight the supporting subgraph.</div>
        </div>
      </section>
    </div>
    <script>
      const statusEl = document.getElementById('status');
      const episodesEl = document.getElementById('episodes');
      const relationsEl = document.getElementById('relations');
      const graphSvgEl = document.getElementById('graphSvg');
      const groundedGraphSvgEl = document.getElementById('groundedGraphSvg');
      const inputEl = document.getElementById('chatInput');
      const knowledgeEl = document.getElementById('knowledgeInput');
      const answerTextEl = document.getElementById('answerText');
      const groundingFactsEl = document.getElementById('groundingFacts');

      async function refreshState() {
        const res = await fetch('/api/state');
        const data = await res.json();
        graphSvgEl.innerHTML = data.svg;
        episodesEl.innerHTML = data.snapshot.episodes.map(
          ep => `<div><strong>${ep.name}</strong><br>${ep.content}</div>`
        ).join('<hr>');
        relationsEl.innerHTML = data.snapshot.relations.length
          ? data.snapshot.relations.map(
              rel => `<div><strong>${rel.relation_name}</strong>: ${rel.fact}</div>`
            ).join('<hr>')
          : '<div>No entity-to-entity relations yet.</div>';
      }

      function renderGrounding(answer) {
        if (!answer) {
          answerTextEl.innerHTML = 'No grounded answer yet.';
          groundingFactsEl.innerHTML = 'No supporting KG slice selected yet.';
          groundedGraphSvgEl.innerHTML = 'Ask a question to highlight the supporting subgraph.';
          return;
        }

        answerTextEl.innerHTML = `<div>${answer.answer}</div>`;
        const facts = answer.used_facts.map(
          fact => `<div><strong>${fact.name}</strong>: ${fact.fact}</div>`
        );
        const nodes = answer.used_nodes.map(
          node => `<div><strong>Node</strong>: ${node.name}</div>`
        );
        const episodes = answer.used_episodes.map(
          episode => `<div><strong>Episode</strong>: ${episode.name} (${episode.source_description})</div>`
        );
        groundingFactsEl.innerHTML = [...facts, ...nodes, ...episodes].join('<hr>') || 'No supporting KG slice selected yet.';
      }

      document.getElementById('addKnowledgeBtn').addEventListener('click', async () => {
        const text = knowledgeEl.value.trim();
        if (!text) return;
        statusEl.textContent = 'Adding prior knowledge...';
        const res = await fetch('/api/knowledge', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text })
        });
        const data = await res.json();
        if (!res.ok) {
          statusEl.textContent = data.detail || 'Failed.';
          return;
        }
        knowledgeEl.value = '';
        statusEl.textContent = 'Prior knowledge stored.';
        await refreshState();
      });

      document.getElementById('sendBtn').addEventListener('click', async () => {
        const text = inputEl.value.trim();
        if (!text) return;
        statusEl.textContent = 'Processing question...';
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text })
        });
        const data = await res.json();
        if (!res.ok) {
          statusEl.textContent = data.detail || 'Failed.';
          return;
        }
        inputEl.value = '';
        statusEl.textContent = `Turn ${data.turn_index} stored.`;
        renderGrounding(data.answer);
        groundedGraphSvgEl.innerHTML = data.grounded_svg;
        await refreshState();
      });

      document.getElementById('resetBtn').addEventListener('click', async () => {
        statusEl.textContent = 'Resetting graph...';
        const res = await fetch('/api/reset', { method: 'POST' });
        const data = await res.json();
        statusEl.textContent = data.message;
        renderGrounding(null);
        await refreshState();
      });

      refreshState();
      setInterval(refreshState, 2000);
    </script>
  </body>
</html>
"""
    return (
        page.replace('__BROWSER_URL__', html.escape(browser_url))
        .replace('__SAGA_NAME__', html.escape(saga_name))
        .replace('__ONE_QUERY__', html.escape(one_neo4j_query))
    )
