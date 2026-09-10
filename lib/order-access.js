'use strict';

// Explicit projection: new internal fields are private unless deliberately added.
function operatorOrder(order) {
  const fields=['id','folio','requested_at','requester_id','priority','classification',
    'asset_id','asset_name','asset_code','reported_failure','actions','status',
    'technician_name','started_at','finished_at','labor_hours','updated_at','validation_status','autonomous_checklist'];
  return Object.fromEntries(fields.filter(key=>Object.hasOwn(order,key)).map(key=>[key,order[key]]));
}
module.exports={operatorOrder};
