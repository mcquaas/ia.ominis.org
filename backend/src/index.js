'use strict';

module.exports = {
  /**
   * An asynchronous register function that runs before
   * your application is initialized.
   */
  register(/* { strapi } */) {},

  /**
   * An asynchronous bootstrap function that runs before
   * your application gets started.
   * This gives you an opportunity to set up your data model,
   * run jobs, or perform some special logic.
   */
  async bootstrap({ strapi }) {
    // Create custom roles on first boot
    await createCustomRoles(strapi);
    
    // Initialize system stats if not exists
    await initializeSystemStats(strapi);
  },
};

/**
 * Create custom roles: Researcher, Admin, SuperAdmin
 */
async function createCustomRoles(strapi) {
  const roleService = strapi.service('plugin::users-permissions.role');
  
  // Define custom roles and their permissions
  const customRoles = [
    {
      name: 'Researcher',
      description: 'Can use the Ominis API for research purposes',
      type: 'researcher',
      permissions: {
        'api::api-key': {
          controllers: {
            'api-key': {
              create: { enabled: true },
              find: { enabled: true },
              findOne: { enabled: true },
              revoke: { enabled: true },
              usage: { enabled: true },
            },
          },
        },
        'api::query-log': {
          controllers: {
            'query-log': {
              // Researchers can only see their own logs
              find: { enabled: false },
            },
          },
        },
      },
    },
    {
      name: 'Admin',
      description: 'Can view RAG/model stats and add sources',
      type: 'admin',
      permissions: {
        'api::api-key': {
          controllers: {
            'api-key': {
              create: { enabled: true },
              find: { enabled: true },
              findOne: { enabled: true },
              revoke: { enabled: true },
              usage: { enabled: true },
            },
          },
        },
        'api::rag-source': {
          controllers: {
            'rag-source': {
              create: { enabled: true },
              find: { enabled: true },
              findOne: { enabled: true },
              update: { enabled: true },
              delete: { enabled: true },
              reindex: { enabled: true },
              stats: { enabled: true },
            },
          },
        },
        'api::system-stat': {
          controllers: {
            'system-stat': {
              find: { enabled: true },
              refresh: { enabled: true },
            },
          },
        },
        'api::query-log': {
          controllers: {
            'query-log': {
              find: { enabled: true },
              findOne: { enabled: true },
              aggregated: { enabled: true },
            },
          },
        },
      },
    },
    {
      name: 'SuperAdmin',
      description: 'Full system access, can manage other users',
      type: 'superadmin',
      permissions: {
        // SuperAdmin gets all permissions (handled separately in Strapi admin)
        'api::api-key': {
          controllers: {
            'api-key': {
              create: { enabled: true },
              find: { enabled: true },
              findOne: { enabled: true },
              update: { enabled: true },
              delete: { enabled: true },
              revoke: { enabled: true },
              validate: { enabled: true },
              usage: { enabled: true },
            },
          },
        },
        'api::rag-source': {
          controllers: {
            'rag-source': {
              create: { enabled: true },
              find: { enabled: true },
              findOne: { enabled: true },
              update: { enabled: true },
              delete: { enabled: true },
              reindex: { enabled: true },
              stats: { enabled: true },
            },
          },
        },
        'api::system-stat': {
          controllers: {
            'system-stat': {
              find: { enabled: true },
              update: { enabled: true },
              refresh: { enabled: true },
            },
          },
        },
        'api::query-log': {
          controllers: {
            'query-log': {
              create: { enabled: true },
              find: { enabled: true },
              findOne: { enabled: true },
              update: { enabled: true },
              delete: { enabled: true },
              aggregated: { enabled: true },
            },
          },
        },
      },
    },
  ];

  for (const roleData of customRoles) {
    try {
      // Check if role exists
      const existingRole = await strapi.db.query('plugin::users-permissions.role').findOne({
        where: { type: roleData.type },
      });

      if (!existingRole) {
        strapi.log.info(`Creating role: ${roleData.name}`);
        
        await strapi.db.query('plugin::users-permissions.role').create({
          data: {
            name: roleData.name,
            description: roleData.description,
            type: roleData.type,
          },
        });
        
        strapi.log.info(`Role ${roleData.name} created successfully`);
      } else {
        strapi.log.info(`Role ${roleData.name} already exists`);
      }
    } catch (error) {
      strapi.log.error(`Error creating role ${roleData.name}:`, error);
    }
  }
}

/**
 * Initialize system stats singleton
 */
async function initializeSystemStats(strapi) {
  try {
    const existing = await strapi.db.query('api::system-stat.system-stat').findOne({});
    
    if (!existing) {
      strapi.log.info('Initializing system stats...');
      
      await strapi.db.query('api::system-stat.system-stat').create({
        data: {
          totalSources: 0,
          indexedSources: 0,
          totalChunks: 0,
          modelVersion: 'ominis-2.0',
          modelStatus: 'offline',
          cpuServerStatus: 'offline',
          gpuServerStatus: 'offline',
          totalQueries24h: 0,
          totalQueriesWeek: 0,
          totalQueriesMonth: 0,
          errorRate24h: 0,
        },
      });
      
      strapi.log.info('System stats initialized');
    }
  } catch (error) {
    strapi.log.error('Error initializing system stats:', error);
  }
}
