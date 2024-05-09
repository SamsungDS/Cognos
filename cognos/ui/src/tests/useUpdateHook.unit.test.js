import '@testing-library/jest-dom/extend-expect';
import useUpdateHook from '../customhooks/useUpdateHook';


describe('useUpdateHook', () => {
    const setMemboxDataMock = jest.fn();
    const setShowFreeMemoryMock = jest.fn();
    const apiEndpointMock = 'http://127.0.0.1:4000';
  
    afterEach(() => {
      jest.clearAllMocks();
    });
  
    it('should handle update successfully', async () => {
      const lmd = 'D-1';
      const mem_mode = 'Shared';
  
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ someData: 'memboxData' })
      });
  
      const { handleUpdate } = useUpdateHook(setMemboxDataMock, setShowFreeMemoryMock, apiEndpointMock);
      await handleUpdate(lmd, mem_mode);
  
      expect(setShowFreeMemoryMock).toHaveBeenCalledTimes(1);
      expect(fetch).toHaveBeenCalledWith(`${apiEndpointMock}/update_lmd`, {
        mode: 'cors',
        method: 'PUT',
        headers: { 'Content-Type': 'application/json',  'Access-Control-Allow-Origin':'*' },
        body: JSON.stringify({ lmd, mem_mode })
      });
      expect(setMemboxDataMock).toHaveBeenCalledWith({ someData: 'memboxData' });
    });
  
    it('should handle update failure', async () => {
      const lmd = 'D-1';
      const mem_mode = 'Shared';
  
      global.fetch = jest.fn().mockRejectedValue(new Error('Failed to fetch'));
  
      const { handleUpdate } = useUpdateHook(setMemboxDataMock, setShowFreeMemoryMock, apiEndpointMock);
      await handleUpdate(lmd, mem_mode);
  
      expect(setShowFreeMemoryMock).toHaveBeenCalledTimes(1);
      expect(fetch).toHaveBeenCalledWith(`${apiEndpointMock}/update_lmd`, {
        mode: 'cors',
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin':'*' },
        body: JSON.stringify({ lmd, mem_mode })
      });
      expect(setMemboxDataMock).not.toHaveBeenCalled();
    });
  });