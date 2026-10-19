# AI Workflow Rescue

AI Workflow Rescue is an AI-powered application that helps detect, investigate, and recover from failures in automated workflows.

The application demonstrates a simple order-processing system:

**Validate Order → Reserve Inventory → Generate Invoice**

If a workflow fails, the system automatically retries temporary errors. For complex failures, an AI agent investigates the issue and suggests a recovery action.

Manual recovery requires admin approval to prevent unsafe operations.

## Tech Stack

- **Backend:** Python, FastAPI
- **Frontend:** React, TypeScript
- **Database:** PostgreSQL
- **Background Tasks:** Redis, Celery
- **AI:** Gemini, LangGraph
- **Deployment:** Docker, Docker Compose

## Key Features

- Automated workflow processing and retries
- AI-powered failure investigation
- Safe recovery without duplicate operations
- Admin approval for manual recovery
- Workflow monitoring and execution history
- Inventory release when an order cannot be completed

## How to Run the Application

### Prerequisites

Install the following:

- Docker with Docker Compose
- GNU Make

### Step 1: Start the application

Open a terminal in the project folder and run:

```bash
make up
```

This starts all the required services.

### Step 2: Create demo users

```bash
make seed
```

This creates the operator and admin accounts. Their login credentials will be displayed in the terminal.

### Step 3: Open the application

Open your browser and visit:

**http://127.0.0.1:3000**

Log in using the credentials generated in Step 2.

### Step 4: Enable AI Investigation (Optional)

Add your Gemini API key to the `.env` file:

```env
GEMINI_API_KEY=your_api_key
```

Restart the application:

```bash
make up
```

Run the demo with AI investigation:

```bash
make demo DEMO_ARGS=--investigate
```

The application also works without a Gemini API key, but AI investigations will not be available.

## Demo Scenarios

| Scenario | Description |
|---|---|
| Normal Order | Order completes successfully |
| Temporary Failure | Automatically retries and completes |
| Repeated Failure | Stops after the retry limit |
| Permanent Failure | Stops without retrying |
| Uncertain Outcome | Verifies an existing reservation before resuming |
| Invoice Failure | Releases reserved inventory through approved recovery |

## How AI Is Used

Gemini and LangGraph investigate failed workflows and recommend possible recovery actions.

**AI does not directly execute recovery operations.** Backend safety checks and human approval control manual recovery.

## Project Goal

The goal of AI Workflow Rescue is to make automated workflows more reliable by combining AI-assisted investigation with safe, controlled recovery.
