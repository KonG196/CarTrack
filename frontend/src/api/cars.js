import client from './client';

export async function getCars() {
  const { data } = await client.get('/cars');
  return data;
}

export async function getCar(carId) {
  const { data } = await client.get(`/cars/${carId}`);
  return data;
}

export async function createCar(payload) {
  const { data } = await client.post('/cars', payload);
  return data;
}

export async function updateCar(carId, payload) {
  const { data } = await client.patch(`/cars/${carId}`, payload);
  return data;
}

export async function deleteCar(carId) {
  await client.delete(`/cars/${carId}`);
}
