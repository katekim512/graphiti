import html
from datetime import datetime
from typing import Any

ONE_NEO4J_QUERY = """MATCH (s:Saga {name: "__SAGA_NAME__"})-[:HAS_EPISODE]->(e:Episodic)
MATCH p=(e)-[:MENTIONS]->(n:Entity)
RETURN p
UNION
MATCH (s:Saga {name: "__SAGA_NAME__"})-[:HAS_EPISODE]->(:Episodic)-[:MENTIONS]->(n:Entity)
MATCH p=(n)-[:RELATES_TO]->(m:Entity)
RETURN p"""

TYPE_ORDER = [
    'Book',
    'GenrePreference',
    'TonePreference',
    'PacingPreference',
    'TimeContext',
    'NegativePreference',
    'Entity',
]

TYPE_TITLES = {
    'Book': 'Books',
    'GenrePreference': 'Genre',
    'TonePreference': 'Tone',
    'PacingPreference': 'Pacing',
    'TimeContext': 'Time',
    'NegativePreference': 'Avoid / Constraint',
    'Entity': 'Other',
}

PROVENANCE_COLORS = {
    'prior': '#cfeee2',
    'question': '#dbe8ff',
    'shared': '#efdaf7',
    'time': '#e6dcff',
    'other': '#fbe8c7',
}


def get_entity_type(labels: list[str]) -> str:
    for entity_type in TYPE_ORDER:
        if entity_type in labels:
            return entity_type
    return 'Entity'


def render_svg(snapshot: dict[str, Any], highlighted: dict[str, set[str]] | None = None) -> str:
    episodes = snapshot['episodes']
    mentions = snapshot['mentions']
    relations = snapshot['relations']
    highlighted = highlighted or {}
    highlighted_entity_uuids = highlighted.get('entity_uuids', set())
    highlighted_relation_uuids = highlighted.get('relation_uuids', set())

    entity_uuid_by_name: dict[str, str] = {}
    entity_labels_by_name: dict[str, list[str]] = {}
    entity_sources_by_name: dict[str, set[str]] = {}
    episode_source_by_uuid = {
        row['uuid']: row.get('source_description', '') for row in episodes if row.get('uuid')
    }

    for row in mentions:
        entity_name = row.get('entity')
        entity_uuid = row.get('entity_uuid')
        if not entity_name or not entity_uuid:
            continue
        entity_uuid_by_name[entity_name] = entity_uuid
        entity_labels_by_name[entity_name] = row.get('labels', [])
        source_description = episode_source_by_uuid.get(row.get('episode_uuid'), '')
        entity_sources_by_name.setdefault(entity_name, set()).add(source_description)

    for rel in relations:
        entity_uuid_by_name.setdefault(rel['source'], rel['source_uuid'])
        entity_uuid_by_name.setdefault(rel['target'], rel['target_uuid'])
        entity_labels_by_name.setdefault(rel['source'], rel.get('source_labels', ['Entity']))
        entity_labels_by_name.setdefault(rel['target'], rel.get('target_labels', ['Entity']))
        relation_sources = set()
        for episode_uuid in rel.get('episodes', []) or []:
            relation_sources.add(episode_source_by_uuid.get(episode_uuid, ''))
        if relation_sources:
            entity_sources_by_name.setdefault(rel['source'], set()).update(relation_sources)
            entity_sources_by_name.setdefault(rel['target'], set()).update(relation_sources)

    typed_entities: dict[str, list[str]] = {entity_type: [] for entity_type in TYPE_ORDER}
    for entity_name in sorted(entity_uuid_by_name.keys()):
        entity_type = get_entity_type(entity_labels_by_name.get(entity_name, ['Entity']))
        typed_entities.setdefault(entity_type, []).append(entity_name)

    entity_positions: dict[str, tuple[int, int]] = {}
    width = 2060
    top = 150
    row_gap = 112
    col_x = {
        'Book': 180,
        'GenrePreference': 470,
        'TonePreference': 760,
        'PacingPreference': 1050,
        'TimeContext': 1340,
        'NegativePreference': 1630,
        'Entity': 1920,
    }

    max_rows = 1
    for entity_type in TYPE_ORDER:
        entities = typed_entities.get(entity_type, [])
        max_rows = max(max_rows, len(entities))
        for row_index, entity in enumerate(entities):
            entity_positions[entity] = (col_x[entity_type], top + row_index * row_gap)

    height = max(top + max_rows * row_gap + 140, 460)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" xmlns="http://www.w3.org/2000/svg">',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#54606b"/></marker></defs>',
        '<rect width="100%" height="100%" fill="#fbfaf7"/>',
        '<text x="60" y="35" font-size="26" font-family="NanumSquare, Apple SD Gothic Neo, Malgun Gothic, sans-serif" fill="#1f2933">Realtime KG Snapshot</text>',
        '<text x="60" y="58" font-size="14" font-family="Menlo, monospace" fill="#52606d">Entity-only view grouped by node type and colored by provenance</text>',
    ]

    for entity_type in TYPE_ORDER:
        x = col_x[entity_type]
        parts.append(
            f'<text x="{x}" y="95" text-anchor="middle" font-size="16" font-family="Menlo, monospace" fill="#334e68">{TYPE_TITLES[entity_type]}</text>'
        )

    for rel_index, rel in enumerate(relations):
        source_type = get_entity_type(entity_labels_by_name.get(rel['source'], ['Entity']))
        target_type = get_entity_type(entity_labels_by_name.get(rel['target'], ['Entity']))
        sx, sy = entity_positions.get(rel['source'], (col_x[source_type], top))
        tx, ty = entity_positions.get(rel['target'], (col_x[target_type], top))
        is_highlighted = rel['uuid'] in highlighted_relation_uuids
        offset = 50 + (rel_index % 4) * 16
        control_x1 = sx + offset
        control_x2 = tx - offset
        parts.append(
            f'<path d="M {sx} {sy} C {control_x1} {sy}, {control_x2} {ty}, {tx} {ty}" fill="none" stroke="{"#b42318" if is_highlighted else "#d64545"}" stroke-width="{"5" if is_highlighted else "2.5"}" marker-end="url(#arrow)" opacity="0.88" />'
        )
        label_x = (sx + tx) / 2
        label_y = (sy + ty) / 2 - 10 - (rel_index % 2) * 10
        parts.append(
            f'<rect x="{label_x - 58}" y="{label_y - 12}" width="116" height="18" rx="8" ry="8" fill="#fbfaf7" opacity="0.92" />'
        )
        parts.append(
            f'<text x="{label_x}" y="{label_y}" text-anchor="middle" font-size="10" font-family="Menlo, monospace" fill="#9b1c1c">{html.escape(rel["relation_name"])}</text>'
        )

    for entity, (x, y) in entity_positions.items():
        entity_uuid = entity_uuid_by_name.get(entity)
        is_highlighted = entity_uuid in highlighted_entity_uuids
        entity_type = get_entity_type(entity_labels_by_name.get(entity, ['Entity']))
        source_tags = entity_sources_by_name.get(entity, set())
        if entity_type == 'TimeContext':
            fill_color = PROVENANCE_COLORS['time']
        elif source_tags == {'prior knowledge'}:
            fill_color = PROVENANCE_COLORS['prior']
        elif source_tags == {'live realtime graph demo'}:
            fill_color = PROVENANCE_COLORS['question']
        elif 'prior knowledge' in source_tags and 'live realtime graph demo' in source_tags:
            fill_color = PROVENANCE_COLORS['shared']
        else:
            fill_color = PROVENANCE_COLORS['other']
        parts.append(
            f'<rect x="{x - 120}" y="{y - 28}" rx="18" ry="18" width="240" height="56" fill="{fill_color}" opacity="0.98" stroke="{"#7c2d12" if is_highlighted else "#d9a514"}" stroke-width="{"4" if is_highlighted else "1.5"}"/>'
        )
        parts.append(
            f'<text x="{x}" y="{y + 5}" text-anchor="middle" font-size="13" font-family="NanumSquare, Apple SD Gothic Neo, Malgun Gothic, sans-serif" fill="#102a43">{html.escape(entity)}</text>'
        )

    parts.append('</svg>')
    return ''.join(parts)


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
