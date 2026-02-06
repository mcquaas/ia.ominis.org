'use strict';

/**
 * Policy to check if user owns the resource or is Admin/SuperAdmin
 */

module.exports = async (policyContext, config, { strapi }) => {
  const { user } = policyContext.state;
  
  if (!user) {
    return false;
  }

  const userRole = user.role?.type || user.role?.name?.toLowerCase();
  
  // Admins can access anything
  if (['admin', 'superadmin'].includes(userRole?.toLowerCase())) {
    return true;
  }

  // For non-admins, check ownership (this requires the route to set owner info)
  const { id } = policyContext.params;
  const { contentType } = config;
  
  if (!id || !contentType) {
    return false;
  }

  try {
    const entity = await strapi.db.query(contentType).findOne({
      where: { id },
      populate: ['owner'],
    });

    return entity?.owner?.id === user.id;
  } catch (error) {
    strapi.log.error('Error checking ownership:', error);
    return false;
  }
};
