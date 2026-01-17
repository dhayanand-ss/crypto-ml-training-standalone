# API Endpoint Documentation

This document provides in-depth documentation for the implementation of the following API endpoints: `/trl`, `/prices/{coin}`, `/last_success`, and `/status` (including `/status/events` and `/status/batch_status`).

## 1. `/prices/{coin}`

**Method:** `GET`

**Description:**
Retrieves historical price data and model predictions for a specific cryptocurrency. It supports filtering by time range, aggregation by time interval, and sampling.

**Parameters:**

| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `coin` | Path | Yes | The cryptocurrency symbol (e.g., `BTCUSDT`). Case-insensitive (converted to uppercase internally). |
| `start` | Query | Yes | Start timestamp for the data range (ISO 8601 format recommended). |
| `end` | Query | Yes | End timestamp for the data range (ISO 8601 format recommended). |
| `interval` | Query | No | Aggregation interval (e.g., `1h`, `1d`). If provided, data is resampled. |
| `step` | Query | No | Sampling step. Returns every Nth row. Default is `1` (all rows). |

**Internal Logic:**

1.  **Data Synchronization:**
    *   Calls `sync_data_periodic()` to check for new successful post-training tasks and trigger a full data sync if needed.
    *   Calls `update_price_periodic()` to fetch recent price updates from the database into the in-memory `state["prices"]`.

2.  **Data Retrieval & Filtering:**
    *   Retrieves the DataFrame for the requested `coin` from the global `state` dictionary.
    *   Filters the DataFrame based on the provided `start` and `end` timestamps.

3.  **Aggregation (Optional):**
    *   If `interval` is provided, the data is resampled using Pandas `resample`.
    *   **Aggregation Rules:**
        *   `open`: First value
        *   `high`: Max value
        *   `low`: Min value
        *   `close`: Last value
        *   `volume`: Sum
        *   Model predictions (`tst_*`, `lightgbm_*`): Last value

4.  **Formatting:**
    *   Converts prediction columns (which might be NumPy arrays) to Python lists for JSON serialization.
    *   Formats the `open_time` column to an ISO 8601 string (`%Y-%m-%dT%H:%M:%SZ`).

5.  **Sampling (Optional):**
    *   If `step` > 1, slices the DataFrame to return every `step`-th row.

**Response:**
A JSON array of objects, where each object represents a data point (candle) with price data and model predictions.

---

## 2. `/trl`

**Method:** `GET`

**Description:**
Retrieves TRL (Trading Reinforcement Learning) data, including news titles, links, dates, and model predictions.

**Parameters:**

| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `start` | Query | Yes | Start timestamp for the data range. |
| `end` | Query | Yes | End timestamp for the data range. |

**Internal Logic:**

1.  **Data Synchronization:**
    *   Triggers `sync_data_periodic()` and `update_trl_periodic()` to ensure data is up-to-date.

2.  **Data Retrieval & Filtering:**
    *   Retrieves the TRL DataFrame from `state["trl"]`.
    *   Filters rows where the `date` falls within the `start` and `end` range.

3.  **Column Selection:**
    *   Selects specific columns: `title`, `link`, `date`, and any columns starting with `trl_` (predictions).

4.  **Validation:**
    *   Checks for invalid numeric values (NaN, infinity) and logs a warning if found.

**Response:**
A JSON array of objects containing TRL data entries.

---

## 3. `/last_success`

**Method:** `GET`

**Description:**
Returns information about the last successful post-training task and the synchronization status.

**Parameters:** None

**Internal Logic:**

1.  **Query:**
    *   Calls `get_last_successful_post_train()`.
    *   Executes a SQL query on the `crypto_batch_status` table:
        ```sql
        SELECT task_name, MAX(updated_at) AS last_success
        FROM crypto_batch_status
        WHERE task_name LIKE 'post_train_%' AND status = 'SUCCESS'
        GROUP BY task_name
        ORDER BY last_success DESC
        LIMIT 1
        ```

**Response:**
A JSON object with the following fields:
*   `last_success`: Timestamp of the last successful post-train task.
*   `task_name`: Name of the task.
*   `overall_last_sync`: Timestamp of the last full data synchronization performed by the API.

---

## 4. `/status` Endpoints

There is no single `/status` endpoint. Instead, the API provides specific status endpoints for monitoring batch processes and events.

### A. `/status/events`

**Method:** `GET`

**Description:**
Retrieves a log of batch events from the `crypto_batch_events` table.

**Parameters:**

| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `dag_name` | Query | No | Filter by DAG name. |
| `task_name` | Query | No | Filter by task name. |
| `limit` | Query | No | Limit the number of records returned. |

**Internal Logic:**
*   Constructs a dynamic SQL query based on provided parameters.
*   Orders results by `created_at` descending.

### B. `/status/batch_status`

**Method:** `GET`

**Description:**
Retrieves the current status of batch tasks from the `crypto_batch_status` table.

**Parameters:**

| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `task_name` | Query | No | Filter by task name. |
| `dag_name` | Query | No | Filter by DAG name. |
| `limit` | Query | No | Limit the number of records returned. |

**Internal Logic:**
*   Constructs a dynamic SQL query based on provided parameters.
*   Orders results by `updated_at` descending.

### C. `/health`

**Method:** `GET`

**Description:**
Simple health check endpoint.

**Response:** `{"status": "ok"}`
