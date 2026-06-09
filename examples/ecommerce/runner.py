"""
Copyright 2024, Zep Software, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType
from graphiti_core.prompts.models import Message
from graphiti_core.utils.bulk_utils import RawEpisode
from graphiti_core.utils.maintenance.graph_data_operations import clear_data

load_dotenv()

neo4j_uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
neo4j_user = os.environ.get('NEO4J_USER', 'neo4j')
neo4j_password = os.environ.get('NEO4J_PASSWORD', 'password')

CHAT_SAGA = 'Ecommerce product recommendation chat'
EXIT_COMMANDS = {'/exit', '/quit', 'exit', 'quit'}
RECOMMENDATION_FACT_LIMIT = 8
SEARCH_CANDIDATE_LIMIT = 24


class RecommendationResponse(BaseModel):
    message: str = Field(description='A concise response from the product recommendation assistant')


def setup_logging():
    logging.basicConfig(level=logging.ERROR, force=True)


async def add_chat_message(
    client: Graphiti,
    message_number: int,
    speaker: str,
    content: str,
    previous_episode_uuid: str | None,
) -> str:
    result = await client.add_episode(
        name=f'Chat message {message_number}',
        episode_body=f'{speaker}: {content}',
        source=EpisodeType.message,
        reference_time=datetime.now(timezone.utc),
        source_description='Live ecommerce product recommendation chat',
        saga=CHAT_SAGA,
        saga_previous_episode_uuid=previous_episode_uuid,
    )
    return result.episode.uuid


async def generate_recommendation(
    client: Graphiti,
    customer_message: str,
    conversation: list[str],
) -> str:
    search_results = await client.search(
        customer_message,
        num_results=SEARCH_CANDIDATE_LIMIT,
    )
    graph_facts = [
        result.fact
        for result in search_results
        if result.expired_at is None
    ][:RECOMMENDATION_FACT_LIMIT]

    response = await client.llm_client.generate_response(
        [
            Message(
                role='system',
                content=(
                    'You are SalesBot, a concise ecommerce product recommendation assistant. '
                    'Recommend only products supported by the supplied knowledge graph facts. '
                    'Every supplied fact is currently valid; expired facts have been excluded. '
                    'Use known customer preferences, purchases, and allergies. Never recommend a '
                    'material the customer says they are allergic to. If the facts are '
                    'insufficient, ask one focused follow-up question instead of inventing '
                    'product details.'
                ),
            ),
            Message(
                role='user',
                content=f"""
<RECENT_CONVERSATION>
{json.dumps(conversation[-8:], ensure_ascii=False)}
</RECENT_CONVERSATION>

<CUSTOMER_MESSAGE>
{customer_message}
</CUSTOMER_MESSAGE>

<KNOWLEDGE_GRAPH_FACTS>
{json.dumps(graph_facts, ensure_ascii=False)}
</KNOWLEDGE_GRAPH_FACTS>

Reply naturally as SalesBot without adding a speaker prefix.
""",
            ),
        ],
        response_model=RecommendationResponse,
        prompt_name='ecommerce.live_recommendation',
    )
    return RecommendationResponse(**response).message.strip()


async def run_live_chat(client: Graphiti):
    greeting = 'Hi, I can help you find a product from the Manybirds catalog.'
    print('\n[Status] Building the initial chat graph...')

    conversation = [f'SalesBot: {greeting}']
    previous_episode_uuid = await add_chat_message(
        client,
        message_number=0,
        speaker='SalesBot',
        content=greeting,
        previous_episode_uuid=None,
    )

    print('[Status] Initial chat graph complete.')
    print(f'\nSalesBot: {greeting}')
    print(
        'Tell me what you need, including preferences such as material, color, size, or allergies.'
    )
    print('Type /exit to finish.\n')

    message_number = 1

    while True:
        print('[Status] Waiting for your message.')
        try:
            customer_message = (await asyncio.to_thread(input, 'Customer: ')).strip()
        except (EOFError, KeyboardInterrupt):
            print('\nSalesBot: Thanks for chatting. Your conversation is stored in the graph.')
            return

        if not customer_message:
            continue
        if customer_message.lower() in EXIT_COMMANDS:
            print('SalesBot: Thanks for chatting. Your conversation is stored in the graph.')
            return

        conversation.append(f'Customer: {customer_message}')
        print('[Status] Building the graph from your message...')

        previous_episode_uuid = await add_chat_message(
            client,
            message_number,
            'Customer',
            customer_message,
            previous_episode_uuid,
        )
        message_number += 1

        print('[Status] Waiting for the recommendation response...')
        recommendation = await generate_recommendation(client, customer_message, conversation)
        conversation.append(f'SalesBot: {recommendation}')

        print('[Status] Building the graph from the recommendation response...')
        previous_episode_uuid = await add_chat_message(
            client,
            message_number,
            'SalesBot',
            recommendation,
            previous_episode_uuid,
        )
        message_number += 1
        print('[Status] Graph update complete.')
        print(f'\nSalesBot: {recommendation}\n')


async def main():
    setup_logging()
    client = Graphiti(neo4j_uri, neo4j_user, neo4j_password)
    try:
        print('[Status] Building the product knowledge graph...')
        await clear_data(client.driver)
        await client.build_indices_and_constraints()
        await ingest_products_data(client)
        print('[Status] Product knowledge graph complete.')
        await run_live_chat(client)
    finally:
        await client.close()


async def ingest_products_data(client: Graphiti):
    script_dir = Path(__file__).parent
    json_file_path = script_dir / '../data/manybirds_products.json'

    with open(json_file_path) as file:
        products = json.load(file)['products']

    episodes: list[RawEpisode] = [
        RawEpisode(
            name=f'Product {i}',
            content=str(product),
            source_description='Allbirds products',
            source=EpisodeType.json,
            reference_time=datetime.now(timezone.utc),
        )
        for i, product in enumerate(products)
    ]

    for episode in episodes:
        await client.add_episode(
            episode.name,
            episode.content,
            episode.source_description,
            episode.reference_time,
            episode.source,
        )


if __name__ == '__main__':
    asyncio.run(main())
