# SAP S/4HANA MCP Server

An MCP (Model Context Protocol) server that connects AI assistants (Claude, Joule, etc.) to SAP S/4HANA Cloud, enabling natural language operations on Sales Orders, Purchase Orders, and Production Orders via OData APIs.

## Features

| Module | Operations |
|--------|-----------|
| Sales Orders | List, Get, Create, Update (header & items) |
| Purchase Orders | List, Get, Create, Update (header & items) |
| Production Orders | List, Get, Create, Update, Release, Technically Complete |
| Teams Notifications | Optional push via Power Automate Flow |

## Prerequisites

- Python 3.10+
- SAP S/4HANA Cloud system with the following Communication Scenarios enabled:
  - `SAP_COM_0109` — Sales Order Integration
  - `SAP_COM_0102` — Purchase Order Integration
  - `SAP_COM_0218` — Production Order Integration

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-username/sap-mcp-server.git
cd sap-mcp-server

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables
cp .env.example .env
# Edit .env with your SAP system details
```

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```env
# SAP S/4HANA Cloud API base URLs
SAP_BASE_URL=https://your-system-api.s4hana.cloud.sap/sap/opu/odata/sap/API_SALES_ORDER_SRV
SAP_PO_BASE_URL=https://your-system-api.s4hana.cloud.sap/sap/opu/odata4/sap/api_purchaseorder_2/srvd_a2x/sap/purchaseorder/0001
SAP_PROD_BASE_URL=https://your-system-api.s4hana.cloud.sap/sap/opu/odata/sap/API_PRODUCTION_ORDER_2_SRV

# SAP credentials (Communication User)
SAP_USERNAME=your_communication_user
SAP_PASSWORD=your_password

# Optional: Microsoft Teams notifications via Power Automate
TEAMS_FLOW_URL=
```

> **How to find your API URLs:**
> In SAP S/4HANA Cloud, go to **Communication Arrangements** → open the relevant arrangement → copy the Service URL.

## Usage

### Start the server

```bash
# Load .env and start
python -c "from dotenv import load_dotenv; load_dotenv()" && python sap_mcp_server.py

# Or set env vars manually (Windows)
set SAP_BASE_URL=https://...
set SAP_USERNAME=...
set SAP_PASSWORD=...
python sap_mcp_server.py
```

The server runs at `http://127.0.0.1:8000/mcp`

### Connect to Joule Work Desktop

1. Open **Joule Work Desktop** → Extensions → Connectors → New
2. Set Server URL: `http://127.0.0.1:8000/mcp`
3. Save and enable the connector

### Connect to Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "sap": {
      "command": "python",
      "args": ["path/to/sap_mcp_server.py"],
      "env": {
        "SAP_BASE_URL": "https://your-system-api.s4hana.cloud.sap/...",
        "SAP_USERNAME": "your_user",
        "SAP_PASSWORD": "your_password"
      }
    }
  }
}
```

## Available Tools

### Sales Orders
- `list_sales_orders(top, filter)` — List sales orders
- `get_sales_order(sales_order)` — Get order details
- `list_sales_order_items(sales_order)` — Get order line items
- `create_sales_order(...)` — Create a new sales order
- `update_sales_order(...)` — Update order header
- `update_sales_order_item(...)` — Update order line item

### Purchase Orders
- `list_purchase_orders(top, filter)` — List purchase orders
- `get_purchase_order(purchase_order)` — Get order details
- `list_purchase_order_items(purchase_order)` — Get order line items
- `create_purchase_order(...)` — Create a new purchase order
- `update_purchase_order(...)` — Update order header
- `update_purchase_order_item(...)` — Update order line item

### Production Orders
- `list_production_orders(top, filter)` — List production orders
- `get_production_order(manufacturing_order)` — Get order details
- `list_production_order_components(manufacturing_order)` — Get BOM components
- `create_production_order(...)` — Create a new production order
- `update_production_order(...)` — Update production order
- `release_production_order(manufacturing_order)` — Release order
- `technically_complete_production_order(manufacturing_order)` — TECO order

## SAP System Setup

### Create Communication User
1. In SAP S/4HANA Cloud, open **Communication Systems** → New
2. Set a System ID and Host Name
3. Add an Inbound Communication User (username/password authentication)

### Create Communication Arrangement
1. Open **Communication Arrangements** → New
2. Select the Communication Scenario (e.g., `SAP_COM_0109`)
3. Assign the Communication System created above
4. Note the generated OData Service URL

## License

MIT
