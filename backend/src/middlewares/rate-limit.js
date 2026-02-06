'use strict';

/**
 * Rate limiting middleware
 * Limits requests based on IP or API key
 */

// In-memory store (use Redis in production for distributed systems)
const requestStore = new Map();

// Clean up old entries periodically
setInterval(() => {
  const now = Date.now();
  for (const [key, data] of requestStore.entries()) {
    if (now - data.windowStart > 3600000) { // 1 hour
      requestStore.delete(key);
    }
  }
}, 60000); // Every minute

module.exports = (config, { strapi }) => {
  const defaultConfig = {
    windowMs: 60000, // 1 minute default
    max: 100, // 100 requests per window
    message: 'Too many requests, please try again later.',
    statusCode: 429,
    keyGenerator: (ctx) => {
      // Use API key if present, otherwise IP
      const apiKey = ctx.request.headers['x-api-key'];
      if (apiKey) {
        return `apikey:${apiKey.substring(0, 12)}`;
      }
      return `ip:${ctx.request.ip}`;
    },
    skip: () => false,
    ...config,
  };

  return async (ctx, next) => {
    // Check if should skip
    if (defaultConfig.skip(ctx)) {
      return next();
    }

    const key = defaultConfig.keyGenerator(ctx);
    const now = Date.now();

    // Get or create request data
    let requestData = requestStore.get(key);
    
    if (!requestData || now - requestData.windowStart > defaultConfig.windowMs) {
      // New window
      requestData = {
        count: 0,
        windowStart: now,
      };
    }

    requestData.count++;
    requestStore.set(key, requestData);

    // Set rate limit headers
    const remaining = Math.max(0, defaultConfig.max - requestData.count);
    const resetTime = Math.ceil((requestData.windowStart + defaultConfig.windowMs - now) / 1000);
    
    ctx.set('X-RateLimit-Limit', String(defaultConfig.max));
    ctx.set('X-RateLimit-Remaining', String(remaining));
    ctx.set('X-RateLimit-Reset', String(resetTime));

    // Check if over limit
    if (requestData.count > defaultConfig.max) {
      ctx.status = defaultConfig.statusCode;
      ctx.body = {
        error: {
          status: defaultConfig.statusCode,
          name: 'TooManyRequests',
          message: defaultConfig.message,
          details: {
            retryAfter: resetTime,
          },
        },
      };
      return;
    }

    await next();
  };
};
