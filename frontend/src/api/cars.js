import client from './client';

export function withRole(car) {
  return car?.your_role ? car : { ...car, your_role: 'owner' };
}

export async function getCars() {
  const { data } = await client.get('/cars');
  return data.map(withRole);
}

export async function getCar(carId) {
  const { data } = await client.get(`/cars/${carId}`);
  return withRole(data);
}

export async function createCar(payload) {
  const { data } = await client.post('/cars', payload);
  return withRole(data);
}

export async function updateCar(carId, payload) {
  const { data } = await client.patch(`/cars/${carId}`, payload);
  return withRole(data);
}

export async function deleteCar(carId) {
  await client.delete(`/cars/${carId}`);
}

export async function lookupPlate(query, byVin = false) {
  const { data } = await client.post('/plate/lookup', { query, by_vin: byVin });
  return data;
}
