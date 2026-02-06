'use strict';

/**
 * API Key authentication middleware
 * Validates API keys for external API access
 */

const bcrypt = require('bcryptjs');

module.exports = (config, { strapi }) => {
  const defaultConfig = {
    header: 'x-api-key',
    required: true,
    ...config,
  };

  return async (ctx, next) => {
    const apiKey = ctx.request.headers[defaultConfig.header];

    // If API key not required and not provided, continue
    if (!defaultConfig.required && !apiKey) {
      return next();
    }

    // If required but not provided
    if (defaultConfig.required && !apiKey) {
      ctx.status = 401;
      ctx.body = {
        error: {
          status: 401,
          name: 'UnauthorizedError',
          message: 'API key is required',
        },
      };
      return;
    }

    try {
      // Validate API key
      const keyPrefix = apiKey.substring(0, 12);
      
      // Find potential matches by prefix
      const candidates = await strapi.db.query('api::api-key.api-key').findMany({
        where: { 
          keyPrefix,
          status: 'active',
        },
        populate: ['owner'],
      });

      let validKey = null;
      
      // Verify the full key hash
      for (const candidate of candidates) {
        const isValid = await bcrypt.compare(apiKey, candidate.keyHash);
        
        if (isValid) {
          validKey = candidate;
          break;
        }
      }

      if (!validKey) {
        ctx.status = 401;
        ctx.body = {
          error: {
            status: 401,
            name: 'UnauthorizedError',
            message: 'Invalid API key',
          },
        };
        return;
      }

      // Check expiration
      if (validKey.expiresAt && new Date(validKey.expiresAt) < new Date()) {
        await strapi.db.query('api::api-key.api-key').update({
          where: { id: validKey.id },
          data: { status: 'expired' },
        });
        
        ctx.status = 401;
        ctx.body = {
          error: {
            status: 401,
            name: 'UnauthorizedError',
            message: 'API key has expired',
          },
        };
        return;
      }

      // Check IP whitelist if configured
      if (validKey.ipWhitelist && validKey.ipWhitelist.length > 0) {
        const clientIp = ctx.request.ip;
        if (!validKey.ipWhitelist.includes(clientIp)) {
          ctx.status = 403;
          ctx.body = {
            error: {
              status: 403,
              name: 'ForbiddenError',
              message: 'IP address not allowed',
            },
          };
          return;
        }
      }

      // Update usage stats (async, don't wait)
      strapi.db.query('api::api-key.api-key').update({
        where: { id: validKey.id },
        data: {
          requestsCount: (parseInt(validKey.requestsCount) || 0) + 1,
          lastUsedAt: new Date(),
        },
      }).catch(err => strapi.log.error('Failed to update API key usage:', err));

      // Attach API key info to context
      ctx.state.apiKey = {
        id: validKey.id,
        name: validKey.name,
        owner: validKey.owner,
        permissions: validKey.permissions,
        rateLimit: validKey.rateLimit,
        rateLimitWindow: validKey.rateLimitWindow,
      };

      await next();
    } catch (error) {
      strapi.log.error('API key validation error:', error);
      ctx.status = 500;
      ctx.body = {
        error: {
          status: 500,
          name: 'InternalServerError',
          message: 'Error validating API key',
        },
      };
    }
  };
};
