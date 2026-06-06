import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from graphiti_core import Graphiti
from graphiti_core.driver.neo4j_driver import Neo4jDriver
from graphiti_core.nodes import EpisodeType
from graphiti_core.prompts.models import Message
from graphiti_core.search.search_config import SearchResults
from graphiti_core.search.search_config_recipes import COMBINED_HYBRID_SEARCH_RRF
from graphiti_core.utils.maintenance.graph_data_operations import clear_data

load_dotenv()

NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD')
NEO4J_DATABASE = os.environ.get('NEO4J_DATABASE', 'neo4j')
NEO4J_BROWSER_URL = os.environ.get('NEO4J_BROWSER_URL', 'http://127.0.0.1:7474/browser/')
SAGA_NAME = 'book_reco_live_demo'
PRIOR_KNOWLEDGE_SAGA_NAME = 'book_reco_prior_knowledge'

graphiti: Graphiti | None = None


class Book(BaseModel):
    """A specific book title that the user has read, liked, disliked, or wants recommended."""


class GenrePreference(BaseModel):
    """A genre, subgenre, or thematic reading preference such as emotional SF, mystery, or romance."""


class TonePreference(BaseModel):
    """A preferred emotional tone such as hopeful, warm, dark, bleak, uplifting, or gentle."""


class PacingPreference(BaseModel):
    """A preference about pacing or reading tempo such as slow burn, fast paced, or reflective."""


class NegativePreference(BaseModel):
    """A disliked element or avoided constraint such as dystopian, too dark, horror, or dense prose."""


class LikesBookEdge(BaseModel):
    """User likes or positively evaluates a specific book title."""


class PrefersGenreEdge(BaseModel):
    """User prefers a genre, subgenre, or thematic reading category."""


class PrefersToneEdge(BaseModel):
    """User prefers a particular emotional tone or atmosphere."""


class PrefersPacingEdge(BaseModel):
    """User prefers a certain pacing style such as slow burn or fast paced."""


class AvoidsElementEdge(BaseModel):
    """User wants to avoid a specific unwanted reading element or mood."""


class HasGenreEdge(BaseModel):
    """A book belongs to or strongly matches a genre or thematic category."""


class HasToneEdge(BaseModel):
    """A book has a particular emotional tone or atmosphere."""


class HasPacingEdge(BaseModel):
    """A book has a characteristic pacing style."""


class LacksElementEdge(BaseModel):
    """A book lacks or avoids an unwanted element such as dystopian darkness."""


ENTITY_TYPES = {
    'Book': Book,
    'GenrePreference': GenrePreference,
    'TonePreference': TonePreference,
    'PacingPreference': PacingPreference,
    'NegativePreference': NegativePreference,
}

EDGE_TYPES = {
    'LIKES_BOOK': LikesBookEdge,
    'PREFERS_GENRE': PrefersGenreEdge,
    'PREFERS_TONE': PrefersToneEdge,
    'PREFERS_PACING': PrefersPacingEdge,
    'AVOIDS_ELEMENT': AvoidsElementEdge,
    'HAS_GENRE': HasGenreEdge,
    'HAS_TONE': HasToneEdge,
    'HAS_PACING': HasPacingEdge,
    'LACKS_ELEMENT': LacksElementEdge,
}

EDGE_TYPE_MAP = {
    ('Entity', 'Book'): ['LIKES_BOOK'],
    ('Entity', 'GenrePreference'): ['PREFERS_GENRE'],
    ('Entity', 'TonePreference'): ['PREFERS_TONE'],
    ('Entity', 'PacingPreference'): ['PREFERS_PACING'],
    ('Entity', 'NegativePreference'): ['AVOIDS_ELEMENT'],
    ('Book', 'GenrePreference'): ['HAS_GENRE'],
    ('Book', 'TonePreference'): ['HAS_TONE'],
    ('Book', 'PacingPreference'): ['HAS_PACING'],
    ('Book', 'NegativePreference'): ['LACKS_ELEMENT'],
}

CUSTOM_EXTRACTION_INSTRUCTIONS = """
This is a live book recommendation conversation.

Extraction goals:
- Extract concrete book titles as Book.
- Extract stated liked genres/themes as GenrePreference.
- Extract preferred mood words as TonePreference.
- Extract pacing preferences as PacingPreference.
- Extract dislikes, avoided moods, and avoided subgenres as NegativePreference.
- For book catalog entries, connect Book entities to genre, tone, pacing, and avoidance entities.
- Prefer specific preference entities over vague nouns.
- When the speaker is the user, preserve preference facts as explicit relations whenever possible.
- Treat the user as a stable speaker entity and connect that speaker entity to preferences and books.
- If a relation matches one of the provided FACT_TYPES, prefer that exact relation type name.
- Book titles should remain specific titles, never generalized to "book" or "novel".
""".strip()


class GroundedRecommendation(BaseModel):
    answer: str
    recommended_titles: list[str] = Field(default_factory=list)
    supporting_fact_indices: list[int] = Field(default_factory=list)
    supporting_node_indices: list[int] = Field(default_factory=list)
    supporting_episode_indices: list[int] = Field(default_factory=list)

STRUCTURED_PREFIX = """
BOOK_RECOMMENDATION_PROFILE
- Extract a stable user entity from first-person statements.
- Interpret each line below as an explicit fact candidate.
""".strip()


def structure_episode_body(text: str) -> str:
    raw = text.strip()
    lower = raw.lower()
    lines = [STRUCTURED_PREFIX, f'- RAW_USER_MESSAGE: {raw}']

    preference_keywords = ['좋아', '선호', '원해', '좋았어', '좋았다', '마음에 들어']
    avoid_keywords = ['싫어', '피하고', '원치 않아', '부담', 'too dark', 'dystopian']

    if any(keyword in raw for keyword in preference_keywords):
        lines.append(f'- USER_STATED_PREFERENCE: {raw}')
    if any(keyword in raw for keyword in avoid_keywords):
        lines.append(f'- USER_STATED_AVOIDANCE: {raw}')

    if 'tone' in lower or '분위기' in raw:
        lines.append(f'- TONE_PREFERENCE_CANDIDATE: {raw}')
    if 'pacing' in lower or '전개' in raw or 'slow burn' in lower or 'fast paced' in lower:
        lines.append(f'- PACING_PREFERENCE_CANDIDATE: {raw}')
    if 'sf' in lower or 'sci-fi' in lower or 'genre' in lower or '장르' in raw:
        lines.append(f'- GENRE_PREFERENCE_CANDIDATE: {raw}')

    return '\n'.join(lines)


def require_env() -> None:
    if not NEO4J_PASSWORD:
        raise RuntimeError('NEO4J_PASSWORD is missing')
    if not os.environ.get('OPENAI_API_KEY'):
        raise RuntimeError('OPENAI_API_KEY is missing')


async def get_graphiti() -> Graphiti:
    global graphiti
    if graphiti is None:
        require_env()
        graphiti = Graphiti(
            graph_driver=Neo4jDriver(
                uri=NEO4J_URI,
                user=NEO4J_USER,
                password=NEO4J_PASSWORD,
                database=NEO4J_DATABASE,
            )
        )
        await graphiti.build_indices_and_constraints()
    return graphiti


async def snapshot_graph(client: Graphiti) -> dict[str, Any]:
    episode_records, _, _ = await client.driver.execute_query(
        """
        MATCH (e:Episodic)
        RETURN e.uuid AS uuid, e.name AS name, e.content AS content, e.valid_at AS valid_at, e.source_description AS source_description
        ORDER BY e.valid_at ASC, e.created_at ASC
        """
    )
    mention_records, _, _ = await client.driver.execute_query(
        """
        MATCH (e:Episodic)-[m:MENTIONS]->(n:Entity)
        RETURN e.uuid AS episode_uuid, e.name AS episode, n.uuid AS entity_uuid, n.name AS entity, labels(n) AS labels
        ORDER BY episode, entity
        """
    )
    relation_records, _, _ = await client.driver.execute_query(
        """
        MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
        RETURN
            r.uuid AS uuid,
            a.uuid AS source_uuid,
            a.name AS source,
            r.name AS relation_name,
            r.fact AS fact,
            b.uuid AS target_uuid,
            b.name AS target
        ORDER BY source, relation_name, target
        """
    )
    return {
        'episodes': [dict(record) for record in episode_records],
        'mentions': [dict(record) for record in mention_records],
        'relations': [dict(record) for record in relation_records],
    }


async def add_prior_knowledge(text: str) -> dict[str, Any]:
    client = await get_graphiti()
    snapshot_before = await snapshot_graph(client)
    item_index = len(snapshot_before['episodes']) + 1
    structured_body = '\n'.join(
        [
            'BOOK_RECOMMENDATION_PRIOR_KNOWLEDGE',
            '- Interpret each line below as durable prior knowledge.',
            f'- RAW_KNOWLEDGE: {text.strip()}',
        ]
    )

    result = await client.add_episode(
        name=f'knowledge_{item_index}',
        episode_body=structured_body,
        source=EpisodeType.text,
        source_description='prior knowledge',
        reference_time=datetime.now(timezone.utc),
        group_id=NEO4J_DATABASE,
        saga=PRIOR_KNOWLEDGE_SAGA_NAME,
        entity_types=ENTITY_TYPES,
        edge_types=EDGE_TYPES,
        edge_type_map=EDGE_TYPE_MAP,
        custom_extraction_instructions=CUSTOM_EXTRACTION_INSTRUCTIONS,
    )
    snapshot_after = await snapshot_graph(client)
    return {
        'episode_uuid': result.episode.uuid,
        'nodes': [node.name for node in result.nodes],
        'edges': [edge.fact for edge in result.edges],
        'snapshot': snapshot_after,
    }


def build_grounding_context(search_results: SearchResults, question: str) -> list[Message]:
    fact_lines = []
    for index, edge in enumerate(search_results.edges):
        fact_lines.append(f'FACT[{index}] name={edge.name} fact={edge.fact}')

    node_lines = []
    for index, node in enumerate(search_results.nodes):
        node_lines.append(f'NODE[{index}] name={node.name} summary={node.summary}')

    episode_lines = []
    for index, episode in enumerate(search_results.episodes):
        episode_lines.append(
            f'EPISODE[{index}] source_description={episode.source_description} content={episode.content}'
        )

    return [
        Message(
            role='system',
            content=(
                'You are a grounded book recommendation assistant. '
                'Use only the provided graph context. Recommend at most two books. '
                'If evidence is weak, say that briefly. '
                'Always return valid JSON matching the schema.'
            ),
        ),
        Message(
            role='user',
            content=(
                f'User request: {question}\n\n'
                'Relevant graph facts:\n'
                + '\n'.join(fact_lines or ['FACT[0] none'])
                + '\n\nRelevant graph nodes:\n'
                + '\n'.join(node_lines or ['NODE[0] none'])
                + '\n\nRelevant graph episodes:\n'
                + '\n'.join(episode_lines or ['EPISODE[0] none'])
                + '\n\nReturn a concise recommendation answer and cite only the indices you actually used.'
            ),
        ),
    ]


async def generate_grounded_answer(client: Graphiti, question: str) -> dict[str, Any]:
    search_config = COMBINED_HYBRID_SEARCH_RRF.model_copy(deep=True)
    search_config.limit = 8
    search_results = await client.search_(
        question,
        config=search_config,
        group_ids=[NEO4J_DATABASE],
    )

    response = await client.llm_client.generate_response(
        build_grounding_context(search_results, question),
        response_model=GroundedRecommendation,
        group_id=NEO4J_DATABASE,
        prompt_name='book_recommendation.grounded_answer',
    )

    grounded = GroundedRecommendation.model_validate(response)

    used_edges = [
        search_results.edges[index]
        for index in grounded.supporting_fact_indices
        if 0 <= index < len(search_results.edges)
    ]
    used_nodes = [
        search_results.nodes[index]
        for index in grounded.supporting_node_indices
        if 0 <= index < len(search_results.nodes)
    ]
    used_episodes = [
        search_results.episodes[index]
        for index in grounded.supporting_episode_indices
        if 0 <= index < len(search_results.episodes)
    ]

    return {
        'answer': grounded.answer,
        'recommended_titles': grounded.recommended_titles,
        'used_edge_uuids': [edge.uuid for edge in used_edges],
        'used_entity_uuids': sorted(
            {
                edge.source_node_uuid
                for edge in used_edges
                if edge.source_node_uuid is not None
            }
            | {
                edge.target_node_uuid
                for edge in used_edges
                if edge.target_node_uuid is not None
            }
            | {node.uuid for node in used_nodes}
        ),
        'used_episode_uuids': [episode.uuid for episode in used_episodes],
        'used_facts': [
            {'name': edge.name, 'fact': edge.fact, 'uuid': edge.uuid}
            for edge in used_edges
        ],
        'used_nodes': [
            {'name': node.name, 'summary': node.summary, 'uuid': node.uuid}
            for node in used_nodes
        ],
        'used_episodes': [
            {
                'name': episode.name,
                'content': episode.content,
                'uuid': episode.uuid,
                'source_description': episode.source_description,
            }
            for episode in used_episodes
        ],
    }


async def add_chat_turn(text: str) -> dict[str, Any]:
    client = await get_graphiti()
    snapshot_before = await snapshot_graph(client)
    turn_index = len(snapshot_before['episodes']) + 1
    structured_body = structure_episode_body(text)

    result = await client.add_episode(
        name=f'live_turn_{turn_index}',
        episode_body=structured_body,
        source=EpisodeType.message,
        source_description='live realtime graph demo',
        reference_time=datetime.now(timezone.utc),
        group_id=NEO4J_DATABASE,
        saga=SAGA_NAME,
        entity_types=ENTITY_TYPES,
        edge_types=EDGE_TYPES,
        edge_type_map=EDGE_TYPE_MAP,
        custom_extraction_instructions=CUSTOM_EXTRACTION_INSTRUCTIONS,
    )
    snapshot_after = await snapshot_graph(client)
    grounded_answer = await generate_grounded_answer(client, text)
    return {
        'turn_index': turn_index,
        'episode_uuid': result.episode.uuid,
        'nodes': [node.name for node in result.nodes],
        'edges': [edge.fact for edge in result.edges],
        'snapshot': snapshot_after,
        'grounded_answer': grounded_answer,
    }


async def get_state() -> dict[str, Any]:
    client = await get_graphiti()
    return await snapshot_graph(client)


async def reset_graph() -> dict[str, str]:
    client = await get_graphiti()
    await clear_data(client.driver)
    await client.build_indices_and_constraints()
    return {'message': 'Graph reset complete.'}
