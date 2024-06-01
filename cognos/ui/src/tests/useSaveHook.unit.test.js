import '@testing-library/jest-dom/extend-expect';
import useSaveHook from '../customhooks/useSaveHook';


describe('useSaveHook', () => {
  const setMemboxDataMock = jest.fn();
  const setShowMock = jest.fn();
  const apiEndpointMock = 'http://127.0.0.1:4000//api/v2.0.0';

  afterEach(() => {
    jest.clearAllMocks();
  });

  it('should handle save successfully', async () => {
    // Mock response data
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

    // Mock fetch implementation
    global.fetch = jest.fn().mockImplementation(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve(mockData),
    }));

    // Call the hook function
    const { handleSave } = useSaveHook(setMemboxDataMock, setShowMock, apiEndpointMock);

    // Call the handler function
    await handleSave({ someFormData: 'formData' });

    // Assertions
    expect(setShowMock).toHaveBeenCalledWith(false);
    expect(setMemboxDataMock).toHaveBeenCalledWith(mockData);
  });

  it('should handle save failure', async () => {
    // Mock fetch implementation to simulate failure
    global.fetch = jest.fn().mockImplementation(() => Promise.reject(new Error('Failed to fetch')));

    // Call the hook function
    const { handleSave } = useSaveHook(setMemboxDataMock, setShowMock, apiEndpointMock);

    // Call the handler function
    await handleSave({ someFormData: 'formData' });

    // Assertions
    expect(setShowMock).toHaveBeenCalledWith(false);
    expect(setMemboxDataMock).not.toHaveBeenCalled();
  });
});