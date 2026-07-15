export function expenseCategoryRows(expenseByCategory) {
  if (!expenseByCategory) return [];
  return Object.entries(expenseByCategory)
    .map(([name, total]) => ({ name, total }))
    .sort((a, b) => b.total - a.total || a.name.localeCompare(b.name, 'uk'));
}

export function shouldShowStations(stations) {
  if (!Array.isArray(stations)) return false;
  const refuels = stations.reduce((sum, station) => sum + (station.refuels || 0), 0);
  return refuels >= 2;
}
