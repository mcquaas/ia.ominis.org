'use strict';

/**
 * Migration: Add phone, phoneVerified, emailVerified to users
 * Run: In Strapi, schema changes may auto-sync. For manual migration:
 * npx strapi db:migrate (if using strapi migrations)
 *
 * Or run the SQL directly for PostgreSQL:
 * ALTER TABLE up_users ADD COLUMN IF NOT EXISTS phone VARCHAR(20);
 * ALTER TABLE up_users ADD COLUMN IF NOT EXISTS "phoneVerified" BOOLEAN DEFAULT false;
 * ALTER TABLE up_users ADD COLUMN IF NOT EXISTS "emailVerified" BOOLEAN DEFAULT false;
 */

module.exports = {
  async up(knex) {
    const hasPhone = await knex.schema.hasColumn('up_users', 'phone');
    if (!hasPhone) {
      await knex.schema.alterTable('up_users', (table) => {
        table.string('phone', 20);
        table.boolean('phoneVerified').defaultTo(false);
        table.boolean('emailVerified').defaultTo(false);
      });
    }
  },

  async down(knex) {
    await knex.schema.alterTable('up_users', (table) => {
      table.dropColumn('phone');
      table.dropColumn('phoneVerified');
      table.dropColumn('emailVerified');
    });
  },
};
