# Ominis Admin Backend

Strapi V5 backend for managing the Ominis Health LLM system. Provides user authentication, role-based access control, RAG source management, and API key generation.

## Features

- **User Authentication**: JWT-based authentication with secure password hashing
- **Role-Based Access Control**: Three roles (Researcher, Admin, SuperAdmin)
- **API Key Management**: Generate and manage API keys for external API access
- **RAG Source Management**: Add, edit, and manage sources for the RAG system
- **System Monitoring**: View system stats, query logs, and model status

## Roles

| Role | Capabilities |
|------|-------------|
| **Researcher** | Use Ominis API, manage own API keys |
| **Admin** | All Researcher capabilities + view stats, manage RAG sources |
| **SuperAdmin** | All Admin capabilities + manage users and roles |

## Quick Start

### Prerequisites

- Node.js >= 20.0.0
- npm >= 6.0.0
- PostgreSQL (for production) or SQLite (for development)

### Installation

1. **Install dependencies**:
   ```bash
   cd backend
   npm install
   ```

2. **Generate secure secrets**:
   ```bash
   node scripts/generate-secrets.js
   ```

3. **Create environment file**:
   ```bash
   cp .env.example .env
   # Edit .env with your secrets and configuration
   ```

4. **Start development server**:
   ```bash
   npm run develop
   ```

5. **Access admin panel**: http://localhost:1337/admin

### First-Time Setup

1. Create your first admin account through the Strapi admin panel
2. Configure role permissions in Settings > Users & Permissions > Roles
3. Run the seed script to create custom roles:
   ```bash
   npm run seed
   ```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `HOST` | Server host | `0.0.0.0` |
| `PORT` | Server port | `1337` |
| `APP_KEYS` | Application keys (comma-separated) | Required |
| `ADMIN_JWT_SECRET` | Admin panel JWT secret | Required |
| `API_TOKEN_SALT` | API token salt | Required |
| `JWT_SECRET` | User authentication JWT secret | Required |
| `DATABASE_CLIENT` | Database type (`sqlite` or `postgres`) | `sqlite` |
| `FRONTEND_URL` | Frontend URL for CORS | `http://localhost:3000` |

### Database Configuration

#### SQLite (Development)
```env
DATABASE_CLIENT=sqlite
DATABASE_FILENAME=.tmp/data.db
```

#### PostgreSQL (Production)
```env
DATABASE_CLIENT=postgres
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=ominis_admin
DATABASE_USERNAME=ominis_admin
DATABASE_PASSWORD=your-secure-password
DATABASE_SSL=true
```

## API Endpoints

### Authentication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/auth/local` | POST | Login with email/password |
| `/v1/auth/local/register` | POST | Register new user |
| `/v1/users/me` | GET | Get current user |

### API Keys

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/v1/api-keys` | GET | List user's API keys | JWT |
| `/v1/api-keys` | POST | Create new API key | JWT |
| `/v1/api-keys/:id/revoke` | POST | Revoke an API key | JWT |
| `/v1/api-keys/:id/usage` | GET | Get API key usage stats | JWT |
| `/v1/api-keys/validate` | POST | Validate API key | None |

### RAG Sources (Admin+)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/rag-sources` | GET | List all sources |
| `/v1/rag-sources` | POST | Create new source |
| `/v1/rag-sources/:id` | PUT | Update source |
| `/v1/rag-sources/:id` | DELETE | Delete source |
| `/v1/rag-sources/:id/reindex` | POST | Trigger re-indexing |
| `/v1/rag-sources/stats` | GET | Get source statistics |

### System Stats (Admin+)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/system-stats` | GET | Get system statistics |
| `/v1/system-stats/refresh` | POST | Refresh statistics |
| `/v1/system-stats/health` | GET | Health check (public) |

### Query Logs (Admin+)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/query-logs` | GET | List query logs |
| `/v1/query-logs/aggregated` | GET | Get aggregated stats |

## Using API Keys with Ominis API

When making requests to the Ominis API, include the API key in the header:

```bash
curl -X POST https://api.ominis.org/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ominis_your_api_key_here" \
  -d '{"query": "¿Qué es la diabetes?"}'
```

## Security Features

- **Password Hashing**: bcrypt with salt rounds
- **JWT Tokens**: Configurable expiration (default: 7 days)
- **API Key Hashing**: Keys are hashed before storage, only shown once on creation
- **Rate Limiting**: Configurable per-endpoint rate limits
- **CORS**: Configurable allowed origins
- **IP Whitelisting**: Optional per-API-key IP restrictions

## Development

### Scripts

| Command | Description |
|---------|-------------|
| `npm run develop` | Start with hot reload |
| `npm run start` | Start production server |
| `npm run build` | Build for production |
| `npm run seed` | Seed database with roles and admin |
| `npm run seed:roles` | Seed only roles |

### Project Structure

```
backend/
├── config/           # Strapi configuration
├── database/         # Database migrations
├── public/           # Static files
├── scripts/          # Seed and utility scripts
├── src/
│   ├── api/          # Content types and APIs
│   │   ├── api-key/
│   │   ├── query-log/
│   │   ├── rag-source/
│   │   └── system-stats/
│   ├── admin/        # Admin customizations
│   ├── extensions/   # Plugin extensions
│   ├── middlewares/  # Custom middlewares
│   ├── policies/     # Authorization policies
│   └── index.js      # Bootstrap functions
└── types/            # TypeScript types
```

## Production Deployment

1. Set all environment variables
2. Use PostgreSQL database
3. Enable SSL for database connection
4. Configure proper CORS origins
5. Set strong secrets (use `generate-secrets.js`)
6. Run behind a reverse proxy (nginx)
7. Enable HTTPS

See [../docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md) for detailed deployment instructions.

## License

MIT - See [../LICENSE](../LICENSE)
