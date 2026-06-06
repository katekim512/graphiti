from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from examples.book_recommendation.realtime_graph_page import render_page
from examples.book_recommendation.realtime_graph_service import (
    NEO4J_BROWSER_URL,
    SAGA_NAME,
    add_prior_knowledge,
    add_chat_turn,
    get_state,
    reset_graph,
)
from examples.book_recommendation.realtime_graph_visualization import (
    ONE_NEO4J_QUERY,
    make_json_safe,
    render_svg,
)

app = FastAPI(title='Graphiti Realtime KG Demo')


class ChatRequest(BaseModel):
    text: str


@app.get('/', response_class=HTMLResponse)
async def index() -> str:
    return render_page(
        browser_url=NEO4J_BROWSER_URL,
        saga_name=SAGA_NAME,
        one_neo4j_query=ONE_NEO4J_QUERY.replace('__SAGA_NAME__', SAGA_NAME),
    )


@app.get('/api/state')
async def state() -> dict[str, Any]:
    snapshot = await get_state()
    return {'snapshot': make_json_safe(snapshot), 'svg': render_svg(snapshot)}


@app.post('/api/knowledge')
async def knowledge(request: ChatRequest) -> dict[str, Any]:
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail='text is required')

    result = await add_prior_knowledge(text)
    snapshot = result['snapshot']
    return {
        'episode_uuid': result['episode_uuid'],
        'nodes': result['nodes'],
        'edges': result['edges'],
        'snapshot': make_json_safe(snapshot),
        'svg': render_svg(snapshot),
    }


@app.post('/api/chat')
async def chat(request: ChatRequest) -> dict[str, Any]:
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail='text is required')

    result = await add_chat_turn(text)
    snapshot = result['snapshot']
    grounded_answer = result['grounded_answer']
    grounded_svg = render_svg(
        snapshot,
        highlighted={
            'episode_uuids': set(grounded_answer['used_episode_uuids']),
            'entity_uuids': set(grounded_answer['used_entity_uuids']),
            'relation_uuids': set(grounded_answer['used_edge_uuids']),
        },
    )
    return {
        'turn_index': result['turn_index'],
        'episode_uuid': result['episode_uuid'],
        'nodes': result['nodes'],
        'edges': result['edges'],
        'snapshot': make_json_safe(snapshot),
        'svg': render_svg(snapshot),
        'grounded_svg': grounded_svg,
        'answer': grounded_answer,
    }


@app.post('/api/reset')
async def reset() -> dict[str, str]:
    return await reset_graph()
