'use strict';

/**
 * api-key controller
 */

const { createCoreController } = require('@strapi/strapi').factories;
const crypto = require('crypto');
const bcrypt = require('bcryptjs');

// Generate a secure API key
function generateApiKey() {
  const prefix = 'ominis_';
  const randomBytes = crypto.randomBytes(32).toString('hex');
  return `${prefix}${randomBytes}`;
}

// Hash API key for storage
async function hashApiKey(key) {
  return bcrypt.hash(key, 10);
}

module.exports = createCoreController('api::api-key.api-key', ({ strapi }) => ({
  // Override create to generate and hash API key
  async create(ctx) {
    const { data } = ctx.request.body;
    const user = ctx.state.user;
    
    if (!user) {
      return ctx.unauthorized('You must be logged in to create an API key');
    }
    
    try {
      // Generate new API key
      const rawKey = generateApiKey();
      const keyHash = await hashApiKey(rawKey);
      const keyPrefix = rawKey.substring(0, 12);
      
      // Create the API key entry
      const entity = await strapi.db.query('api::api-key.api-key').create({
        data: {
          ...data,
          keyHash,
          keyPrefix,
          owner: user.id,
          status: 'active',
          requestsCount: 0,
        },
      });
      
      // Return the raw key ONLY on creation (never stored in plain text)
      return ctx.send({
        data: {
          id: entity.id,
          name: entity.name,
          description: entity.description,
          status: entity.status,
          keyPrefix: entity.keyPrefix,
          permissions: entity.permissions,
          rateLimit: entity.rateLimit,
          rateLimitWindow: entity.rateLimitWindow,
          expiresAt: entity.expiresAt,
          createdAt: entity.createdAt,
        },
        // IMPORTANT: This is the only time the full key is returned
        apiKey: rawKey,
        message: 'Store this API key securely. It will not be shown again.',
      });
    } catch (error) {
      ctx.throw(500, error);
    }
  },
  
  // Revoke an API key
  async revoke(ctx) {
    const { id } = ctx.params;
    const user = ctx.state.user;
    
    try {
      const entity = await strapi.db.query('api::api-key.api-key').findOne({
        where: { id },
        populate: ['owner'],
      });
      
      if (!entity) {
        return ctx.notFound('API key not found');
      }
      
      // Check ownership or admin role
      const userRole = user.role?.type || user.role?.name;
      const isOwner = entity.owner?.id === user.id;
      const isAdmin = ['admin', 'superadmin'].includes(userRole?.toLowerCase());
      
      if (!isOwner && !isAdmin) {
        return ctx.forbidden('You can only revoke your own API keys');
      }
      
      await strapi.db.query('api::api-key.api-key').update({
        where: { id },
        data: { status: 'revoked' },
      });
      
      return ctx.send({
        message: 'API key revoked successfully',
        id,
      });
    } catch (error) {
      ctx.throw(500, error);
    }
  },
  
  // Validate an API key (for external API usage)
  async validate(ctx) {
    const { apiKey } = ctx.request.body;
    
    if (!apiKey) {
      return ctx.badRequest('API key is required');
    }
    
    try {
      const keyPrefix = apiKey.substring(0, 12);
      
      // Find potential matches by prefix
      const candidates = await strapi.db.query('api::api-key.api-key').findMany({
        where: { 
          keyPrefix,
          status: 'active',
        },
        populate: ['owner'],
      });
      
      // Verify the full key hash
      for (const candidate of candidates) {
        const isValid = await bcrypt.compare(apiKey, candidate.keyHash);
        
        if (isValid) {
          // Check expiration
          if (candidate.expiresAt && new Date(candidate.expiresAt) < new Date()) {
            await strapi.db.query('api::api-key.api-key').update({
              where: { id: candidate.id },
              data: { status: 'expired' },
            });
            return ctx.send({ valid: false, reason: 'expired' });
          }
          
          // Update usage stats
          await strapi.db.query('api::api-key.api-key').update({
            where: { id: candidate.id },
            data: {
              requestsCount: (parseInt(candidate.requestsCount) || 0) + 1,
              lastUsedAt: new Date(),
            },
          });
          
          return ctx.send({
            valid: true,
            keyId: candidate.id,
            owner: {
              id: candidate.owner?.id,
              email: candidate.owner?.email,
            },
            permissions: candidate.permissions,
            rateLimit: candidate.rateLimit,
            rateLimitWindow: candidate.rateLimitWindow,
          });
        }
      }
      
      return ctx.send({ valid: false, reason: 'invalid' });
    } catch (error) {
      ctx.throw(500, error);
    }
  },
  
  // Get usage statistics for an API key
  async usage(ctx) {
    const { id } = ctx.params;
    const user = ctx.state.user;
    
    try {
      const entity = await strapi.db.query('api::api-key.api-key').findOne({
        where: { id },
        populate: ['owner'],
      });
      
      if (!entity) {
        return ctx.notFound('API key not found');
      }
      
      // Check ownership or admin role
      const userRole = user.role?.type || user.role?.name;
      const isOwner = entity.owner?.id === user.id;
      const isAdmin = ['admin', 'superadmin'].includes(userRole?.toLowerCase());
      
      if (!isOwner && !isAdmin) {
        return ctx.forbidden('You can only view your own API key usage');
      }
      
      return ctx.send({
        id: entity.id,
        name: entity.name,
        requestsCount: entity.requestsCount,
        lastUsedAt: entity.lastUsedAt,
        rateLimit: entity.rateLimit,
        rateLimitWindow: entity.rateLimitWindow,
        status: entity.status,
      });
    } catch (error) {
      ctx.throw(500, error);
    }
  },
}));
