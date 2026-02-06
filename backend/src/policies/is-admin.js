'use strict';

/**
 * Policy to check if user has Admin or SuperAdmin role
 */

module.exports = async (policyContext, config, { strapi }) => {
  const { user } = policyContext.state;
  
  if (!user) {
    return false;
  }

  const userRole = user.role?.type || user.role?.name?.toLowerCase();
  
  return ['admin', 'superadmin'].includes(userRole?.toLowerCase());
};
