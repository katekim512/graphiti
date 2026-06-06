# KG Visualization

현재 `turn_03.json` 기준 전체 그래프 스냅샷입니다.

```mermaid
graph LR
  E1["chat_turn_1"]
  E2["chat_turn_2"]
  E3["chat_turn_3"]

  N1["나는"]
  N2["감정선이 진한 SF 소설"]
  N3["분위기"]
  N4["프로젝트 헤일메리"]
  N5["클라라와 태양"]

  E1 -->|"MENTIONS"| N1
  E1 -->|"MENTIONS"| N2
  E2 -->|"MENTIONS"| N3
  E3 -->|"MENTIONS"| N4
  E3 -->|"MENTIONS"| N5

  N1 -->|"LIKES"| N2
  N4 -->|"HAS_SIMILAR_TONE_WITH"| N5
```

## Reading Guide

- `Episodic` 노드: `chat_turn_1`, `chat_turn_2`, `chat_turn_3`
- `MENTIONS`: 해당 턴에서 어떤 엔티티가 언급되었는지
- `RELATES_TO`: Graphiti가 추출한 구조화된 사실 관계

## Current Snapshot

- Episodes: 3
- Mention edges: 5
- Entity relation edges: 2
