import client from './client';

export async function getYearReview(carId, year) {
  const { data } = await client.get(`/cars/${carId}/year-review`, {
    params: year ? { year } : undefined,
  });
  return data;
}
