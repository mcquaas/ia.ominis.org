# Ominis Health Frontend

Modern web interface for the Ominis Health LLM health Q&A system.

Built with [Next.js](https://nextjs.org) and released by [Fundación Mexicana para la Salud A.C.](https://funsalud.org.mx/) through [ai.ominis.org](https://ai.ominis.org).

## Features

- Modern, responsive chat interface
- Spanish language support
- Source citations display
- Health information Q&A

## Getting Started

### Prerequisites

- Node.js 18+
- npm, yarn, pnpm, or bun

### Development

```bash
# Install dependencies
npm install

# Run development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to view the application.

### Configuration

Set the API endpoint in the application or via environment variables:

```bash
# .env.local
NEXT_PUBLIC_API_URL=https://your-api-endpoint.execute-api.mx-central-1.amazonaws.com/query
```

### Build for Production

```bash
npm run build
npm start
```

## Project Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx      # Root layout
│   │   ├── page.tsx        # Main page
│   │   └── globals.css     # Global styles
│   └── components/
│       ├── ChatInterface.tsx   # Chat UI component
│       ├── Header.tsx          # Page header
│       ├── Footer.tsx          # Page footer
│       ├── Hero.tsx            # Hero section
│       └── Features.tsx        # Features section
├── public/                 # Static assets
└── package.json           # Dependencies
```

## Data Privacy

This frontend connects to the Ominis Health API which runs 100% in Mexico. See the main project [DATA_PRIVACY.md](../docs/DATA_PRIVACY.md) for details.

## License

Copyright 2026 Fundación Mexicana para la Salud A.C.

Licensed under the Apache License, Version 2.0. See [LICENSE](../LICENSE) for details.
