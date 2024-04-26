import '@testing-library/jest-dom/extend-expect';
import useDeleteHook from '../customhooks/useDeleteHook';

describe('useDeleteHook', () => {
    const setMemboxDataMock = jest.fn();
    const setShowFreeMemoryMock = jest.fn();
    const apiEndpointMock = 'http://127.0.0.1:4000';
  
    afterEach(() => {
      jest.clearAllMocks();
    });
  
    it('should handle deletion successfully', async () => {
      const item = { lmd: 'D-1' };
  
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ someData: 'memboxData' })
      });
  
      const { handleDelete } = useDeleteHook(setMemboxDataMock, setShowFreeMemoryMock, apiEndpointMock);
      await handleDelete(item);
  
      expect(setShowFreeMemoryMock).toHaveBeenCalledTimes(1);
      expect(fetch).toHaveBeenCalledWith(`${apiEndpointMock}/free_lmd`, {
        mode: 'cors',
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(item)
      });
      expect(setMemboxDataMock).toHaveBeenCalledWith({ someData: 'memboxData' });
    });
  
    it('should handle deletion failure', async () => {
      const item = { lmd: 'D-1' };
  
      global.fetch = jest.fn().mockRejectedValue(new Error('Failed to fetch'));
  
      const { handleDelete } = useDeleteHook(setMemboxDataMock, setShowFreeMemoryMock, apiEndpointMock);
      await handleDelete(item);
  
      expect(setShowFreeMemoryMock).toHaveBeenCalledTimes(1);
      expect(fetch).toHaveBeenCalledWith(`${apiEndpointMock}/free_lmd`, {
        mode: 'cors',
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(item)
      });
      expect(setMemboxDataMock).not.toHaveBeenCalled();
    });
  });