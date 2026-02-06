# Ominis Admin API Documentation

Documentación completa del API de Strapi para integración con el frontend.

**Base URL**: `https://admin.ominis.org/v1`

## Tabla de Contenidos

- [Autenticación](#autenticación)
- [Usuarios](#usuarios)
- [API Keys](#api-keys)
- [RAG Sources](#rag-sources-admin)
- [System Stats](#system-stats-admin)
- [Query Logs](#query-logs-admin)
- [Ejemplos de Integración](#ejemplos-de-integración)

---

## Autenticación

Strapi usa JWT (JSON Web Tokens) para autenticación. El token se obtiene al hacer login y debe incluirse en el header `Authorization` de todas las peticiones protegidas.

### Registro de Usuario

```http
POST /v1/auth/local/register
Content-Type: application/json
```

**Request Body:**
```json
{
  "username": "investigador1",
  "email": "investigador@ejemplo.com",
  "password": "MiPassword123!"
}
```

**Response (200 OK):**
```json
{
  "jwt": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "id": 1,
    "username": "investigador1",
    "email": "investigador@ejemplo.com",
    "provider": "local",
    "confirmed": true,
    "blocked": false,
    "createdAt": "2026-02-06T12:00:00.000Z",
    "updatedAt": "2026-02-06T12:00:00.000Z"
  }
}
```

**Errores posibles:**
| Código | Mensaje | Causa |
|--------|---------|-------|
| 400 | Email already taken | El email ya está registrado |
| 400 | Username already taken | El username ya existe |
| 400 | password must be at least 6 characters | Password muy corto |

---

### Login

```http
POST /v1/auth/local
Content-Type: application/json
```

**Request Body:**
```json
{
  "identifier": "investigador@ejemplo.com",
  "password": "MiPassword123!"
}
```

> **Nota**: `identifier` puede ser email o username

**Response (200 OK):**
```json
{
  "jwt": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "id": 1,
    "username": "investigador1",
    "email": "investigador@ejemplo.com",
    "provider": "local",
    "confirmed": true,
    "blocked": false,
    "createdAt": "2026-02-06T12:00:00.000Z",
    "updatedAt": "2026-02-06T12:00:00.000Z"
  }
}
```

**Errores posibles:**
| Código | Mensaje | Causa |
|--------|---------|-------|
| 400 | Invalid identifier or password | Credenciales incorrectas |
| 400 | Your account has been blocked | Usuario bloqueado |

---

### Recuperar Contraseña

#### Solicitar reset de contraseña

```http
POST /v1/auth/forgot-password
Content-Type: application/json
```

**Request Body:**
```json
{
  "email": "investigador@ejemplo.com"
}
```

**Response (200 OK):**
```json
{
  "ok": true
}
```

#### Resetear contraseña

```http
POST /v1/auth/reset-password
Content-Type: application/json
```

**Request Body:**
```json
{
  "code": "código-del-email",
  "password": "NuevaPassword123!",
  "passwordConfirmation": "NuevaPassword123!"
}
```

---

### Cambiar Contraseña (autenticado)

```http
POST /v1/auth/change-password
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "currentPassword": "PasswordActual123!",
  "password": "NuevaPassword123!",
  "passwordConfirmation": "NuevaPassword123!"
}
```

**Response (200 OK):**
```json
{
  "jwt": "nuevo-jwt-token...",
  "user": { ... }
}
```

---

## Usuarios

### Obtener Usuario Actual

```http
GET /v1/users/me?populate=role
Authorization: Bearer <jwt_token>
```

**Response (200 OK):**
```json
{
  "id": 1,
  "username": "investigador1",
  "email": "investigador@ejemplo.com",
  "provider": "local",
  "confirmed": true,
  "blocked": false,
  "role": {
    "id": 3,
    "name": "Researcher",
    "description": "Can use the Ominis API for research purposes",
    "type": "researcher"
  },
  "createdAt": "2026-02-06T12:00:00.000Z",
  "updatedAt": "2026-02-06T12:00:00.000Z"
}
```

---

### Actualizar Perfil

```http
PUT /v1/users/:id
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "username": "nuevo_username",
  "email": "nuevo@email.com"
}
```

> **Nota**: Solo puedes actualizar tu propio perfil (a menos que seas SuperAdmin)

---

## API Keys

Los API Keys permiten autenticar llamadas al Ominis API sin usar el JWT.

### Listar API Keys del Usuario

```http
GET /v1/api-keys?populate=owner
Authorization: Bearer <jwt_token>
```

**Response (200 OK):**
```json
{
  "data": [
    {
      "id": 1,
      "attributes": {
        "name": "Mi API Key de Producción",
        "description": "Para la app móvil",
        "keyPrefix": "ominis_abc1",
        "status": "active",
        "permissions": {
          "query": true,
          "queryGpu": false,
          "sources": false
        },
        "rateLimit": 100,
        "rateLimitWindow": "hour",
        "requestsCount": "1523",
        "lastUsedAt": "2026-02-06T11:30:00.000Z",
        "expiresAt": null,
        "createdAt": "2026-02-01T10:00:00.000Z"
      }
    }
  ],
  "meta": {
    "pagination": {
      "page": 1,
      "pageSize": 25,
      "pageCount": 1,
      "total": 1
    }
  }
}
```

---

### Crear API Key

```http
POST /v1/api-keys
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "data": {
    "name": "API Key para App Móvil",
    "description": "Usada en la aplicación iOS",
    "permissions": {
      "query": true,
      "queryGpu": false,
      "sources": false
    },
    "rateLimit": 100,
    "rateLimitWindow": "hour",
    "expiresAt": "2027-01-01T00:00:00.000Z"
  }
}
```

**Response (200 OK):**
```json
{
  "data": {
    "id": 2,
    "name": "API Key para App Móvil",
    "description": "Usada en la aplicación iOS",
    "keyPrefix": "ominis_def2",
    "status": "active",
    "permissions": {
      "query": true,
      "queryGpu": false,
      "sources": false
    },
    "rateLimit": 100,
    "rateLimitWindow": "hour",
    "expiresAt": "2027-01-01T00:00:00.000Z",
    "createdAt": "2026-02-06T12:00:00.000Z"
  },
  "apiKey": "ominis_def23456789abcdef0123456789abcdef0123456789abcdef0123456789abcd",
  "message": "Store this API key securely. It will not be shown again."
}
```

> ⚠️ **IMPORTANTE**: El campo `apiKey` solo se muestra UNA VEZ al crear la key. Guárdala de forma segura.

---

### Revocar API Key

```http
POST /v1/api-keys/:id/revoke
Authorization: Bearer <jwt_token>
```

**Response (200 OK):**
```json
{
  "message": "API key revoked successfully",
  "id": 2
}
```

---

### Ver Uso de API Key

```http
GET /v1/api-keys/:id/usage
Authorization: Bearer <jwt_token>
```

**Response (200 OK):**
```json
{
  "id": 1,
  "name": "Mi API Key",
  "requestsCount": "1523",
  "lastUsedAt": "2026-02-06T11:30:00.000Z",
  "rateLimit": 100,
  "rateLimitWindow": "hour",
  "status": "active"
}
```

---

### Validar API Key (Público)

Este endpoint es usado internamente por el Ominis API para validar keys.

```http
POST /v1/api-keys/validate
Content-Type: application/json
```

**Request Body:**
```json
{
  "apiKey": "ominis_abc123..."
}
```

**Response (200 OK) - Válida:**
```json
{
  "valid": true,
  "keyId": 1,
  "owner": {
    "id": 1,
    "email": "user@example.com"
  },
  "permissions": {
    "query": true,
    "queryGpu": false,
    "sources": false
  },
  "rateLimit": 100,
  "rateLimitWindow": "hour"
}
```

**Response (200 OK) - Inválida:**
```json
{
  "valid": false,
  "reason": "invalid"
}
```

---

## RAG Sources (Admin+)

Requiere rol **Admin** o **SuperAdmin**.

### Listar Fuentes

```http
GET /v1/rag-sources?populate=addedBy&pagination[page]=1&pagination[pageSize]=25
Authorization: Bearer <jwt_token>
```

**Query Parameters:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `filters[status]` | string | Filtrar por status (pending, processing, indexed, failed, archived) |
| `filters[sourceType]` | string | Filtrar por tipo (tainacan, wordpress, imss_guideline, etc.) |
| `filters[category]` | string | Filtrar por categoría |
| `sort` | string | Ordenar (ej: `createdAt:desc`) |
| `pagination[page]` | number | Página actual |
| `pagination[pageSize]` | number | Items por página (max 100) |

**Response (200 OK):**
```json
{
  "data": [
    {
      "id": 1,
      "attributes": {
        "title": "Guía de Diabetes Mellitus Tipo 2",
        "slug": "guia-diabetes-mellitus-tipo-2",
        "sourceType": "imss_guideline",
        "status": "indexed",
        "sourceUrl": "https://imss.gob.mx/guias/diabetes",
        "chunksCount": 45,
        "lastIndexedAt": "2026-02-05T10:00:00.000Z",
        "category": "chronic_diseases",
        "language": "es-mx",
        "qualityScore": 95.5,
        "createdAt": "2026-02-01T08:00:00.000Z",
        "publishedAt": "2026-02-01T09:00:00.000Z"
      }
    }
  ],
  "meta": {
    "pagination": {
      "page": 1,
      "pageSize": 25,
      "pageCount": 5,
      "total": 120
    }
  }
}
```

---

### Crear Fuente

```http
POST /v1/rag-sources
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "data": {
    "title": "Nueva Guía de Nutrición",
    "sourceType": "manual_upload",
    "content": "Contenido de la guía en texto...",
    "sourceUrl": "https://ejemplo.com/guia.pdf",
    "category": "nutrition",
    "language": "es-mx",
    "notes": "Revisada por Dr. García",
    "metadata": {
      "author": "SSA",
      "year": 2025
    }
  }
}
```

**Response (201 Created):**
```json
{
  "data": {
    "id": 121,
    "attributes": {
      "title": "Nueva Guía de Nutrición",
      "slug": "nueva-guia-de-nutricion",
      "sourceType": "manual_upload",
      "status": "pending",
      "chunksCount": 0,
      ...
    }
  }
}
```

---

### Actualizar Fuente

```http
PUT /v1/rag-sources/:id
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "data": {
    "title": "Título actualizado",
    "status": "archived",
    "notes": "Archivada por estar desactualizada"
  }
}
```

---

### Eliminar Fuente

```http
DELETE /v1/rag-sources/:id
Authorization: Bearer <jwt_token>
```

---

### Re-indexar Fuente

Dispara el proceso de re-indexación para actualizar los embeddings.

```http
POST /v1/rag-sources/:id/reindex
Authorization: Bearer <jwt_token>
```

**Response (200 OK):**
```json
{
  "message": "Re-indexing started",
  "sourceId": 1,
  "status": "processing"
}
```

---

### Estadísticas de Fuentes

```http
GET /v1/rag-sources/stats
Authorization: Bearer <jwt_token>
```

**Response (200 OK):**
```json
{
  "total": 120,
  "byStatus": {
    "indexed": 115,
    "pending": 3,
    "processing": 1,
    "failed": 1
  },
  "totalChunks": 5420
}
```

---

## System Stats (Admin+)

### Obtener Estadísticas del Sistema

```http
GET /v1/system-stat
Authorization: Bearer <jwt_token>
```

**Response (200 OK):**
```json
{
  "data": {
    "id": 1,
    "attributes": {
      "totalSources": 120,
      "indexedSources": 115,
      "totalChunks": 5420,
      "embeddingsSize": "245 MB",
      "faissIndexSize": "128 MB",
      "lastIndexUpdate": "2026-02-06T10:00:00.000Z",
      "modelVersion": "ominis-2.0",
      "modelStatus": "online",
      "cpuServerStatus": "online",
      "gpuServerStatus": "online",
      "avgResponseTimeCpu": 5200,
      "avgResponseTimeGpu": 2100,
      "totalQueries24h": 1523,
      "totalQueriesWeek": 8945,
      "totalQueriesMonth": 32156,
      "errorRate24h": 0.5,
      "lastHealthCheck": "2026-02-06T12:00:00.000Z"
    }
  }
}
```

---

### Refrescar Estadísticas

```http
POST /v1/system-stats/refresh
Authorization: Bearer <jwt_token>
```

**Response (200 OK):**
```json
{
  "message": "Stats refreshed",
  "stats": { ... }
}
```

---

### Health Check (Público)

```http
GET /v1/system-stats/health
```

**Response (200 OK):**
```json
{
  "status": "ok",
  "timestamp": "2026-02-06T12:00:00.000Z",
  "model": {
    "version": "ominis-2.0",
    "status": "online"
  },
  "servers": {
    "cpu": "online",
    "gpu": "online"
  },
  "lastCheck": "2026-02-06T11:55:00.000Z"
}
```

---

## Query Logs (Admin+)

### Estadísticas Agregadas

```http
GET /v1/query-logs/aggregated?period=day
Authorization: Bearer <jwt_token>
```

**Query Parameters:**
| Parámetro | Valores | Default |
|-----------|---------|---------|
| `period` | `hour`, `day`, `week`, `month` | `day` |

**Response (200 OK):**
```json
{
  "period": "day",
  "startDate": "2026-02-05T12:00:00.000Z",
  "endDate": "2026-02-06T12:00:00.000Z",
  "total": 1523,
  "successful": 1510,
  "failed": 13,
  "successRate": 99.15,
  "avgResponseTimeMs": 3250,
  "totalTokens": 245000,
  "byEndpoint": {
    "query": 1200,
    "query-gpu": 323
  }
}
```

---

## Ejemplos de Integración

### React/Next.js - Auth Service

```typescript
// services/auth.ts

const API_URL = 'https://admin.ominis.org/v1';

interface LoginResponse {
  jwt: string;
  user: User;
}

interface User {
  id: number;
  username: string;
  email: string;
  role?: { type: string; name: string };
}

// Login
export async function login(identifier: string, password: string): Promise<LoginResponse> {
  const response = await fetch(`${API_URL}/auth/local`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ identifier, password }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error?.message || 'Login failed');
  }

  const data = await response.json();
  
  // Store token
  localStorage.setItem('token', data.jwt);
  localStorage.setItem('user', JSON.stringify(data.user));
  
  return data;
}

// Register
export async function register(
  username: string, 
  email: string, 
  password: string
): Promise<LoginResponse> {
  const response = await fetch(`${API_URL}/auth/local/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, email, password }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error?.message || 'Registration failed');
  }

  const data = await response.json();
  localStorage.setItem('token', data.jwt);
  localStorage.setItem('user', JSON.stringify(data.user));
  
  return data;
}

// Logout
export function logout(): void {
  localStorage.removeItem('token');
  localStorage.removeItem('user');
}

// Get current user
export async function getMe(): Promise<User> {
  const token = localStorage.getItem('token');
  
  const response = await fetch(`${API_URL}/users/me?populate=role`, {
    headers: { 
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) throw new Error('Not authenticated');
  return response.json();
}

// Check if authenticated
export function isAuthenticated(): boolean {
  return !!localStorage.getItem('token');
}

// Get stored token
export function getToken(): string | null {
  return localStorage.getItem('token');
}
```

### React Hook - useAuth

```typescript
// hooks/useAuth.ts
import { useState, useEffect, createContext, useContext } from 'react';
import * as authService from '@/services/auth';

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (identifier: string, password: string) => Promise<void>;
  register: (username: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  isAdmin: boolean;
  isSuperAdmin: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check if user is logged in on mount
    if (authService.isAuthenticated()) {
      authService.getMe()
        .then(setUser)
        .catch(() => authService.logout())
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = async (identifier: string, password: string) => {
    const { user } = await authService.login(identifier, password);
    setUser(user);
  };

  const register = async (username: string, email: string, password: string) => {
    const { user } = await authService.register(username, email, password);
    setUser(user);
  };

  const logout = () => {
    authService.logout();
    setUser(null);
  };

  const roleType = user?.role?.type?.toLowerCase();
  const isAdmin = ['admin', 'superadmin'].includes(roleType || '');
  const isSuperAdmin = roleType === 'superadmin';

  return (
    <AuthContext.Provider value={{ 
      user, loading, login, register, logout, isAdmin, isSuperAdmin 
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}
```

### Componente Login

```tsx
// components/LoginForm.tsx
'use client';
import { useState } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useRouter } from 'next/navigation';

export function LoginForm() {
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await login(identifier, password);
      router.push('/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label htmlFor="identifier">Email o Usuario</label>
        <input
          id="identifier"
          type="text"
          value={identifier}
          onChange={(e) => setIdentifier(e.target.value)}
          required
          className="w-full p-2 border rounded"
        />
      </div>
      
      <div>
        <label htmlFor="password">Contraseña</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          className="w-full p-2 border rounded"
        />
      </div>

      {error && (
        <div className="text-red-500 text-sm">{error}</div>
      )}

      <button 
        type="submit" 
        disabled={loading}
        className="w-full py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
      >
        {loading ? 'Ingresando...' : 'Ingresar'}
      </button>
    </form>
  );
}
```

### Usar API Key con Ominis API

```typescript
// Usando API Key para consultas
async function queryOminis(question: string, apiKey: string) {
  const response = await fetch('https://api.ominis.org/query', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': apiKey,  // API Key generada desde el admin
    },
    body: JSON.stringify({ question }),
  });

  if (!response.ok) {
    throw new Error('Query failed');
  }

  return response.json();
}
```

---

## Headers Comunes

### Peticiones Autenticadas

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Content-Type: application/json
```

### Respuestas de Error

```json
{
  "error": {
    "status": 401,
    "name": "UnauthorizedError",
    "message": "Invalid token",
    "details": {}
  }
}
```

---

## Códigos de Estado

| Código | Significado |
|--------|-------------|
| 200 | OK - Petición exitosa |
| 201 | Created - Recurso creado |
| 400 | Bad Request - Error en la petición |
| 401 | Unauthorized - No autenticado |
| 403 | Forbidden - Sin permisos |
| 404 | Not Found - Recurso no encontrado |
| 429 | Too Many Requests - Rate limit excedido |
| 500 | Internal Server Error - Error del servidor |

---

## Rate Limiting

Las peticiones están limitadas para prevenir abusos:

| Endpoint | Límite | Ventana |
|----------|--------|---------|
| Auth endpoints | 5 intentos | por minuto |
| API general | 100 peticiones | por minuto |
| API Keys (según config) | Configurable | por hora/día |

Headers de respuesta:
```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 45
```

---

## Variables de Entorno Frontend

```env
# .env.local
NEXT_PUBLIC_STRAPI_URL=https://admin.ominis.org
NEXT_PUBLIC_OMINIS_API_URL=https://api.ominis.org
```
