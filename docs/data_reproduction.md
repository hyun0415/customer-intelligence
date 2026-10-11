# Amazon 리뷰 데이터 재현

이 저장소는 Amazon Reviews 2023 원본이나 가공 Parquet을 재배포하지 않습니다. 대신
공식 원본에서 README의 분석 데이터(상품 547개, 리뷰 105,060개)를 다시 만드는 필터
노트북과 실행 스크립트를 제공합니다.

## 원본 데이터

[Amazon Reviews 2023](https://amazon-reviews-2023.github.io/)에서
`Beauty_and_Personal_Care` 카테고리의 두 파일을 받습니다.

- `meta_Beauty_and_Personal_Care.jsonl.gz`
- `Beauty_and_Personal_Care.jsonl.gz`

원본 파일의 이용 조건은 데이터 제공 페이지를 따릅니다. 원본과 생성된 Parquet은
`data/` 아래에 두며 Git에는 커밋하지 않습니다.

## 필터 기준

1. 상품명에 `shampoo` 또는 `shampoos`가 포함된 상품을 찾습니다.
2. 반려동물·브러시·컨디셔너·드라이 샴푸 등 제외어가 포함된 상품을 제거합니다.
3. Amazon 평점 수가 300개 이상이고 상품 설명이 있는 상품만 남깁니다.
4. 리뷰 50개 이상, 3점 이하 리뷰 10개 이상인 상품만 남깁니다.
5. 한 `parent_asin` 아래 실제 리뷰 `asin`이 하나인 상품만 사용해 변형 상품의 속성
   혼합을 방지합니다.
6. 동일 상품·ASIN·사용자·작성 시각·본문 조합의 중복 리뷰를 제거합니다.

`analyzed_asin`은 필터링된 단일 변형 상품을 확인하기 위한 추적 열입니다. 애플리케이션
DB의 상품 키는 기존과 같이 `parent_asin`이며, 리뷰 원문의 `asin`도 그대로 보존합니다.

## 실행

```powershell
python -m pip install -r requirements-data.txt
python scripts/prepare_amazon_data.py `
  --metadata data/raw/meta_Beauty_and_Personal_Care.jsonl.gz `
  --reviews data/raw/Beauty_and_Personal_Care.jsonl.gz `
  --output-dir data
```

성공하면 다음 파일이 생성됩니다.

- `data/products_rds.parquet`
- `data/reviews_rds.parquet`
- `data/dataset_manifest.json`: 필터 조건, 행 수, 열 목록, 결과 파일 SHA-256

원본 버전이나 처리 환경 차이를 조사할 때만 `--skip-count-check`를 사용합니다. 이 옵션도
관계·집계 검증은 생략하지 않습니다.

## PostgreSQL 적재

로컬 인프라의 DB 마이그레이션이 끝나고 `products`, `reviews` 테이블이 비어 있을 때
다음 명령을 실행합니다.

```powershell
python scripts/load_data.py
```

적재 스크립트는 `analyzed_asin`을 DB 열로 추가하지 않습니다. `products.parent_asin`과
`reviews.parent_asin`의 관계를 확인한 뒤 적재 건수와 연결되지 않은 리뷰 수를 출력합니다.

코드 흐름을 셀 단위로 확인하려면
[`notebooks/01_data_filtering.ipynb`](../notebooks/01_data_filtering.ipynb)를 참고합니다.
