'use strict';

const crypto = require('crypto');

module.exports = (plugin) => {
  // Add custom forgot-password-phone route
  plugin.controllers.auth.forgotPasswordPhone = async (ctx) => {
    const { phone } = ctx.request.body || {};

    if (!phone || typeof phone !== 'string') {
      return ctx.badRequest('Se requiere un número de celular');
    }

    const { strapi } = ctx;
    const pluginStore = await strapi.store({ type: 'plugin', name: 'users-permissions' });
    const advancedSettings = await pluginStore.get({ key: 'advanced' });

    const normalizedPhone = phone.replace(/\D/g, '') || phone;
    const users = await strapi.db
      .query('plugin::users-permissions.user')
      .findMany({
        where: {
          $or: [{ phone: normalizedPhone }, { phone: phone }],
        },
      });
    const user = users[0];

    if (!user || user.blocked) {
      return ctx.send({ ok: true });
    }

    const resetPasswordToken = crypto.randomBytes(64).toString('hex');
    const resetUrl = (advancedSettings.email_reset_password || '').replace(/\/?$/, '');
    const resetLink = `${resetUrl}?code=${resetPasswordToken}`;

    await strapi.db.query('plugin::users-permissions.user').update({
      where: { id: user.id },
      data: { resetPasswordToken },
    });

    const accountSid = process.env.TWILIO_ACCOUNT_SID;
    const authToken = process.env.TWILIO_AUTH_TOKEN;
    const fromNumber = process.env.TWILIO_PHONE_NUMBER;

    if (accountSid && authToken && fromNumber) {
      try {
        const twilio = require('twilio');
        const client = twilio(accountSid, authToken);
        await client.messages.create({
          body: `Ominis: Restablece tu contraseña en ${resetLink}`,
          from: fromNumber,
          to: user.phone,
        });
      } catch (err) {
        strapi.log.error('Twilio SMS failed:', err);
        return ctx.badRequest('No se pudo enviar el SMS. Verifica la configuración de Twilio.');
      }
    } else {
      strapi.log.warn('Twilio not configured. Phone-based password reset skipped.');
      return ctx.badRequest('El restablecimiento por celular no está configurado. Usa tu email.');
    }

    return ctx.send({ ok: true });
  };

  // Add route
  plugin.routes['content-api'].routes.push({
    method: 'POST',
    path: '/auth/forgot-password-phone',
    handler: 'auth.forgotPasswordPhone',
    config: {
      middlewares: ['plugin::users-permissions.rateLimit'],
      prefix: '',
    },
  });

  return plugin;
};
