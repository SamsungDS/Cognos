import '@testing-library/jest-dom/extend-expect';
import useSaveHook from '../customhooks/useSaveHook';

describe('useSaveHook', () => {
  const setMemboxDataMock = jest.fn();
  const setShowMock = jest.fn();
  const apiEndpointMock = 'http://127.0.0.1:4000/api/v2.0.0';

  afterEach(() => {
    jest.clearAllMocks();
  });

  test('should handle save successfully', async () => {
    const mockData = {
      capacity: 128,
      capacity_units: 'GB',
      lmd: 'D-2',
      mem_mode: 'Direct',
      mem_type: 'CMMD',
      pool: '',
      used_capacity: 0,
      used_capacity_units: 'GB',
    };

    global.fetch = jest.fn().mockImplementation(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve(mockData),
    }));

    const { handleSave } = useSaveHook(setMemboxDataMock, setShowMock, apiEndpointMock);

    await handleSave({ someFormData: 'formData' });

    expect(setShowMock).toHaveBeenCalledWith(false);
    expect(setMemboxDataMock).toHaveBeenCalledWith(mockData);
  });

  test('should handle save failure due to network error', async () => {
    global.fetch = jest.fn().mockImplementation(() => Promise.reject(new Error('Failed to fetch')));

    const { handleSave } = useSaveHook(setMemboxDataMock, setShowMock, apiEndpointMock);

    await handleSave({ someFormData: 'formData' });

    expect(setShowMock).toHaveBeenCalledWith(false);
    expect(setMemboxDataMock).not.toHaveBeenCalled();
  });

  test('should handle save when response is not OK', async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: false });

    const { handleSave } = useSaveHook(setMemboxDataMock, setShowMock, apiEndpointMock);

    await handleSave({ someFormData: 'formData' });

    expect(setShowMock).toHaveBeenCalledWith(false);
    expect(setMemboxDataMock).not.toHaveBeenCalled();
  });

  test('should handle save when JSON parsing fails', async () => {
    global.fetch = jest.fn().mockImplementation(() => Promise.resolve({
      ok: true,
      json: () => Promise.reject(new Error('Failed to parse JSON')),
    }));

    const { handleSave } = useSaveHook(setMemboxDataMock, setShowMock, apiEndpointMock);

    await handleSave({ someFormData: 'formData' });

    expect(setShowMock).toHaveBeenCalledWith(false);
    expect(setMemboxDataMock).not.toHaveBeenCalled();
  });
});