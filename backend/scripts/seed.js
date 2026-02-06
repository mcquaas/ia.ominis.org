#!/usr/bin/env node
'use strict';

/**
 * Main seed script to initialize the database with:
 * - Custom roles (Researcher, Admin, SuperAdmin)
 * - Initial SuperAdmin user
 * - System stats singleton
 * 
 * Run with: npm run seed
 * 
 * Environment variables required:
 * - SUPERADMIN_EMAIL
 * - SUPERADMIN_PASSWORD
 * - SUPERADMIN_FIRSTNAME
 * - SUPERADMIN_LASTNAME
 */

require('dotenv').config();
const strapi = require('@strapi/strapi');
const bcrypt = require('bcryptjs');

async function seed() {
  console.log('🌱 Starting database seeding...\n');
  
  const app = await strapi().load();
  
  try {
    // 1. Create custom roles
    console.log('📋 Creating custom roles...');
    await seedRoles(app);
    
    // 2. Create SuperAdmin user
    console.log('\n👤 Creating SuperAdmin user...');
    await seedSuperAdmin(app);
    
    // 3. Initialize system stats
    console.log('\n📊 Initializing system stats...');
    await seedSystemStats(app);
    
    console.log('\n✅ Database seeding completed successfully!');
    console.log('\n📝 Next steps:');
    console.log('   1. Start the server: npm run develop');
    console.log('   2. Access admin panel: http://localhost:1337/admin');
    console.log('   3. Configure role permissions in Settings > Users & Permissions > Roles');
    
  } catch (error) {
    console.error('❌ Seeding failed:', error);
    process.exit(1);
  }
  
  process.exit(0);
}

async function seedRoles(app) {
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
      await app.db.query('plugin::users-permissions.role').create({
        data: role,
      });
      console.log(`   ✓ Created role: ${role.name}`);
    } else {
      console.log(`   • Role exists: ${role.name}`);
    }
  }
}

async function seedSuperAdmin(app) {
  const email = process.env.SUPERADMIN_EMAIL;
  const password = process.env.SUPERADMIN_PASSWORD;
  const firstname = process.env.SUPERADMIN_FIRSTNAME || 'Super';
  const lastname = process.env.SUPERADMIN_LASTNAME || 'Admin';
  
  if (!email || !password) {
    console.log('   ⚠ Skipping SuperAdmin creation (SUPERADMIN_EMAIL and SUPERADMIN_PASSWORD not set)');
    return;
  }
  
  // Validate password strength
  if (password.length < 12) {
    console.log('   ⚠ Warning: Password should be at least 12 characters for production');
  }
  
  // Get or create superadmin role
  let superAdminRole = await app.db.query('plugin::users-permissions.role').findOne({
    where: { type: 'superadmin' },
  });
  
  if (!superAdminRole) {
    superAdminRole = await app.db.query('plugin::users-permissions.role').create({
      data: {
        name: 'SuperAdmin',
        description: 'Full system access',
        type: 'superadmin',
      },
    });
  }
  
  // Check if user exists
  const existingUser = await app.db.query('plugin::users-permissions.user').findOne({
    where: { email: email.toLowerCase() },
  });
  
  if (existingUser) {
    console.log(`   • SuperAdmin already exists: ${email}`);
    return;
  }
  
  // Hash password
  const hashedPassword = await bcrypt.hash(password, 10);
  
  // Create user
  await app.db.query('plugin::users-permissions.user').create({
    data: {
      username: email.split('@')[0],
      email: email.toLowerCase(),
      password: hashedPassword,
      confirmed: true,
      blocked: false,
      role: superAdminRole.id,
    },
  });
  
  console.log(`   ✓ Created SuperAdmin user: ${email}`);
}

async function seedSystemStats(app) {
  const existing = await app.db.query('api::system-stats.system-stats').findOne({});
  
  if (existing) {
    console.log('   • System stats already initialized');
    return;
  }
  
  await app.db.query('api::system-stats.system-stats').create({
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
  
  console.log('   ✓ System stats initialized');
}

seed().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
