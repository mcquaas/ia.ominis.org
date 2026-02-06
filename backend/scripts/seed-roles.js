#!/usr/bin/env node
'use strict';

/**
 * Seed script to ensure custom roles exist
 * Run with: npm run seed:roles
 */

const strapi = require('@strapi/strapi');

async function seedRoles() {
  console.log('Starting role seeding...');
  
  const app = await strapi().load();
  
  const roles = [
    {
      name: 'Researcher',
      description: 'Can use the Ominis API for research purposes. Can create and manage their own API keys.',
      type: 'researcher',
    },
    {
      name: 'Admin', 
      description: 'Can view RAG/model stats, add new sources, and manage researchers.',
      type: 'admin',
    },
    {
      name: 'SuperAdmin',
      description: 'Full system access. Can manage all users, roles, and system configuration.',
      type: 'superadmin',
    },
  ];

  for (const role of roles) {
    const existing = await app.db.query('plugin::users-permissions.role').findOne({
      where: { type: role.type },
    });

    if (!existing) {
      console.log(`Creating role: ${role.name}`);
      await app.db.query('plugin::users-permissions.role').create({
        data: role,
      });
      console.log(`✓ Role ${role.name} created`);
    } else {
      console.log(`✓ Role ${role.name} already exists`);
    }
  }

  console.log('Role seeding completed!');
  process.exit(0);
}

seedRoles().catch((err) => {
  console.error('Error seeding roles:', err);
  process.exit(1);
});
