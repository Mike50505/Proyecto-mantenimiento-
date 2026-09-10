'use strict';
function hoursBetween(startedAt, finishedAt) {
  const start=Date.parse(startedAt),end=Date.parse(finishedAt);
  if(!Number.isFinite(start)||!Number.isFinite(end)||end<=start) {
    throw Object.assign(new Error('La hora final debe ser posterior a la inicial'),{status:400});
  }
  return (end-start)/3600000;
}
module.exports={hoursBetween};
