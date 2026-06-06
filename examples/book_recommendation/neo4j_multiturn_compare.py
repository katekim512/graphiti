import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from graphiti_core import Graphiti
from graphiti_core.driver.neo4j_driver import Neo4jDriver
from graphiti_core.graphiti import AddEpisodeResults
from graphiti_core.nodes import EpisodeType

load_dotenv()

OUTPUT_DIR = Path('examples/book_recommendation/output')

NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD')
NEO4J_DATABASE = os.environ.get('NEO4J_DATABASE', 'neo4j')
RESET_DATABASE = os.environ.get('RESET_DATABASE', '0') == '1'

SAGA_NAME = 'book_reco_chat_demo'

CHAT_TURNS = [
    '나는 감정선이 진한 SF 소설을 좋아해. 너무 어렵지 않았으면 좋겠어.',
    '분위기는 너무 우울하거나 디스토피아적인 건 피하고 싶어. 천천히 몰입되는 전개가 좋아.',
    '프로젝트 헤일메리랑 클라라와 태양은 재미있게 읽었어. 비슷한 결의 추천을 받고 싶어.',
]


def ensure_env() -> None:
    missing = []
    if not NEO4J_PASSWORD:
        missing.append('NEO4J_PASSWORD')
    if not os.environ.get('OPENAI_API_KEY'):
        missing.append('OPENAI_API_KEY')
    if missing:
        raise ValueError(f'Missing required environment variables: {", ".join(missing)}')


def serialize_result(result: AddEpisodeResults) -> dict[str, Any]:
    return {
        'episode': {
            'uuid': result.episode.uuid,
            'name': result.episode.name,
            'content': result.episode.content,
            'source': result.episode.source.value,
            'source_description': result.episode.source_description,
            'valid_at': result.episode.valid_at.isoformat() if result.episode.valid_at else None,
        },
        'nodes': [
            {
                'uuid': node.uuid,
                'name': node.name,
                'labels': node.labels,
                'summary': node.summary,
                'attributes': node.attributes,
            }
            for node in result.nodes
        ],
        'edges': [
            {
                'uuid': edge.uuid,
                'name': edge.name,
                'fact': edge.fact,
                'source_node_uuid': edge.source_node_uuid,
                'target_node_uuid': edge.target_node_uuid,
                'episodes': edge.episodes,
                'valid_at': edge.valid_at.isoformat() if edge.valid_at else None,
                'invalid_at': edge.invalid_at.isoformat() if edge.invalid_at else None,
            }
            for edge in result.edges
        ],
        'episodic_edges': [
            {
                'uuid': edge.uuid,
                'source_node_uuid': edge.source_node_uuid,
                'target_node_uuid': edge.target_node_uuid,
            }
            for edge in result.episodic_edges
        ],
    }


def make_json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: make_json_safe(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [make_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [make_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()

    isoformat = getattr(value, 'isoformat', None)
    if callable(isoformat):
        try:
            return isoformat()
        except TypeError:
            pass

    return value


async def reset_database(graphiti: Graphiti) -> None:
    await graphiti.driver.execute_query(
        """
        MATCH (n)
        DETACH DELETE n
        """
    )


async def snapshot_graph(graphiti: Graphiti) -> dict[str, Any]:
    episode_records, _, _ = await graphiti.driver.execute_query(
        """
        MATCH (e:Episodic)
        RETURN e.uuid AS uuid, e.name AS name, e.content AS content, e.valid_at AS valid_at
        ORDER BY e.valid_at ASC, e.created_at ASC
        """
    )
    mention_records, _, _ = await graphiti.driver.execute_query(
        """
        MATCH (e:Episodic)-[m:MENTIONS]->(n:Entity)
        RETURN e.name AS episode, n.name AS entity, labels(n) AS labels
        ORDER BY episode, entity
        """
    )
    relation_records, _, _ = await graphiti.driver.execute_query(
        """
        MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
        RETURN
            a.name AS source,
            labels(a) AS source_labels,
            r.name AS relation_name,
            r.fact AS fact,
            b.name AS target,
            labels(b) AS target_labels,
            r.valid_at AS valid_at,
            r.invalid_at AS invalid_at
        ORDER BY source, relation_name, target
        """
    )

    return {
        'episodes': [dict(record) for record in episode_records],
        'mentions': [dict(record) for record in mention_records],
        'relations': [dict(record) for record in relation_records],
    }


def write_turn_artifacts(turn_index: int, add_result: AddEpisodeResults, snapshot: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        'turn_index': turn_index,
        'add_episode_result': serialize_result(add_result),
        'graph_snapshot': make_json_safe(snapshot),
    }

    json_path = OUTPUT_DIR / f'turn_{turn_index:02d}.json'
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    md_lines = [
        f'# Turn {turn_index}',
        '',
        '## Added Episode',
        f'- content: {add_result.episode.content}',
        '',
        '## Newly Returned Nodes',
    ]

    for node in add_result.nodes:
        md_lines.append(f'- {node.name} | labels={", ".join(node.labels)}')

    md_lines += ['', '## Newly Returned Entity Edges']

    for edge in add_result.edges:
        md_lines.append(f'- {edge.fact}')

    md_lines += ['', '## Graph Snapshot: Episodic -> Entity (MENTIONS)']

    for row in snapshot['mentions']:
        md_lines.append(f'- {row["episode"]} -> {row["entity"]} ({", ".join(row["labels"])})')

    md_lines += ['', '## Graph Snapshot: Entity -> Entity (RELATES_TO)']

    for row in snapshot['relations']:
        md_lines.append(f'- {row["source"]} -[{row["relation_name"]}]-> {row["target"]}: {row["fact"]}')

    md_path = OUTPUT_DIR / f'turn_{turn_index:02d}.md'
    md_path.write_text('\n'.join(md_lines), encoding='utf-8')


def print_turn_summary(turn_index: int, add_result: AddEpisodeResults, snapshot: dict[str, Any]) -> None:
    print(f'\n===== TURN {turn_index} =====')
    print(add_result.episode.content)
    print('\n[Returned Nodes]')
    for node in add_result.nodes:
        print(f'- {node.name} | labels={node.labels}')
    print('\n[Returned Entity Edges]')
    for edge in add_result.edges:
        print(f'- {edge.fact}')
    print('\n[Current Graph Counts]')
    print(f'- episodes: {len(snapshot["episodes"])}')
    print(f'- mentions: {len(snapshot["mentions"])}')
    print(f'- relations: {len(snapshot["relations"])}')


async def main() -> None:
    ensure_env()

    graphiti = Graphiti(
        graph_driver=Neo4jDriver(
            uri=NEO4J_URI,
            user=NEO4J_USER,
            password=NEO4J_PASSWORD,
            database=NEO4J_DATABASE,
        )
    )

    try:
        await graphiti.build_indices_and_constraints()

        if RESET_DATABASE:
            await reset_database(graphiti)

        reference_time = datetime.now(timezone.utc)
        previous_episode_uuid: str | None = None

        for turn_index, turn in enumerate(CHAT_TURNS, start=1):
            result = await graphiti.add_episode(
                name=f'chat_turn_{turn_index}',
                episode_body=turn,
                source=EpisodeType.message,
                source_description='book recommendation chat',
                reference_time=reference_time + timedelta(minutes=turn_index),
                group_id=NEO4J_DATABASE,
                saga=SAGA_NAME,
                saga_previous_episode_uuid=previous_episode_uuid,
            )
            previous_episode_uuid = result.episode.uuid

            snapshot = await snapshot_graph(graphiti)
            write_turn_artifacts(turn_index, result, snapshot)
            print_turn_summary(turn_index, result, snapshot)

        print(f'\nArtifacts written to: {OUTPUT_DIR}')

    finally:
        await graphiti.close()


if __name__ == '__main__':
    asyncio.run(main())
