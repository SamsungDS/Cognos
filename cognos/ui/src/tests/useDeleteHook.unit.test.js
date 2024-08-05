import '@testing-library/jest-dom/extend-expect';
import useDeleteHook from '../customhooks/useDeleteHook';

describe('useDeleteHook', () => {
    const setMemboxDataMock = jest.fn();
    const setShowFreeMemoryMock = jest.fn();
    const apiEndpointMock = 'http://127.0.0.1:4000';

    afterEach(() => {
      jest.clearAllMocks();
    });

    test('should handle deletion successfully', async () => {
      const item = { dev_name: "DEVX" };

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
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin':'*' },
        body: JSON.stringify(item)
      });
      expect(setMemboxDataMock).toHaveBeenCalledWith({ someData: 'memboxData' });
    });

    test('should handle deletion failure due to network error', async () => {
      const item = { dev_name: "DEVX" };

      global.fetch = jest.fn().mockRejectedValue(new Error('Failed to fetch'));

      const { handleDelete } = useDeleteHook(setMemboxDataMock, setShowFreeMemoryMock, apiEndpointMock);
      await handleDelete(item);

      expect(setShowFreeMemoryMock).toHaveBeenCalledTimes(1);
      expect(fetch).toHaveBeenCalledWith(`${apiEndpointMock}/free_lmd`, {
        mode: 'cors',
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin':'*' },
        body: JSON.stringify(item)
      });
      expect(setMemboxDataMock).not.toHaveBeenCalled();
    });

    test('should handle deletion when response is not OK', async () => {
      const item = { dev_name: "DEVX" };

      global.fetch = jest.fn().mockResolvedValue({ ok: false });

      const { handleDelete } = useDeleteHook(setMemboxDataMock, setShowFreeMemoryMock, apiEndpointMock);
      await handleDelete(item);

      expect(setShowFreeMemoryMock).toHaveBeenCalledTimes(1);
      expect(fetch).toHaveBeenCalledWith(`${apiEndpointMock}/free_lmd`, {
        mode: 'cors',
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin':'*' },
        body: JSON.stringify(item)
      });
      expect(setMemboxDataMock).not.toHaveBeenCalled();
    });

    test('should handle deletion when JSON parsing fails', async () => {
      const item = { dev_name: "DEVX" };

      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.reject(new Error('Failed to parse JSON'))
      });

      const { handleDelete } = useDeleteHook(setMemboxDataMock, setShowFreeMemoryMock, apiEndpointMock);
      await handleDelete(item);

      expect(setShowFreeMemoryMock).toHaveBeenCalledTimes(1);
      expect(fetch).toHaveBeenCalledWith(`${apiEndpointMock}/free_lmd`, {
        mode: 'cors',
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin':'*' },
        body: JSON.stringify(item)
      });
      expect(setMemboxDataMock).not.toHaveBeenCalled();
    });
});