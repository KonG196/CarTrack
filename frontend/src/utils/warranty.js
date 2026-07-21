// Remaining warranty on a repair, or null when it carries none.
//
// Time is the reliable signal (repair date + warranty_months); distance is
// approximate — it needs the car's live odometer and is only shown when both
// the repair odometer and the current one are known. A repair is still covered
// while BOTH the months and the km remain (whichever lapses first ends it).
export function warrantyStatus(
  repair,
  { repairDate, repairOdometer, currentOdometer } = {},
  now = new Date(),
) {
  if (!repair) return null;
  const hasMonths = repair.warranty_months != null;
  const hasKm = repair.warranty_km != null;
  if (!hasMonths && !hasKm) return null;

  let expiry = null;
  let timeActive = true;
  if (hasMonths && repairDate) {
    expiry = new Date(repairDate);
    expiry.setMonth(expiry.getMonth() + repair.warranty_months);
    timeActive = now <= expiry;
  }

  let kmLeft = null;
  let kmActive = true;
  if (hasKm && repairOdometer != null && currentOdometer != null) {
    kmLeft = repairOdometer + repair.warranty_km - currentOdometer;
    kmActive = kmLeft > 0;
  }

  return { active: timeActive && kmActive, expiry, kmLeft };
}
