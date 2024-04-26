import useAttachHook from '../customhooks/useAttachHook';

describe('useAttachHook', () => {
  const setMemboxDataMock = jest.fn();
  const setLmdDataMock = jest.fn();
  const handleAttachMemoryToggleMock = jest.fn();
  const selectedValueMock = { label: 'Host 1' };
  const apiEndpointMock = 'http://105.91.142.222:4000';

  afterEach(() => {
    jest.clearAllMocks();
  });

  it('should handle attachment successfully', async () => {

    const mockLmdData = {
        capacity: 128,
        capacity_units: 'GB',
        lmd: 'D-2',
        mem_mode: 'Direct',
        mem_type: 'CMMD',
        pool: '',
        used_capacity: 0,
        used_capacity_units: 'GB',
      };

    global.fetch = jest.fn().mockImplementation((url) => {
      if (url.endsWith('/attach_lmd')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockLmdData),
        });
      } else if (url.endsWith('/lmds')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ someData: 'memboxData' }),
        });
      } else if (url.endsWith('/activate_device')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ someData: 'activated' }),
        });
      }
    });

    const { handleAttach } = useAttachHook(
      setMemboxDataMock,
      setLmdDataMock,
      handleAttachMemoryToggleMock,
      selectedValueMock,
      apiEndpointMock
    );

    await handleAttach({ someFormData: 'formData' });

    expect(handleAttachMemoryToggleMock).toHaveBeenCalledTimes(1);
    expect(setLmdDataMock).toHaveBeenCalledWith(mockLmdData);
    expect(setMemboxDataMock).toHaveBeenCalledWith({ someData: 'memboxData' });
  });

  it('should handle attachment failure', async () => {
    global.fetch = jest.fn().mockImplementation(() => Promise.reject(new Error('Failed to fetch')));

    const { handleAttach } = useAttachHook(
      setMemboxDataMock,
      setLmdDataMock,
      handleAttachMemoryToggleMock,
      selectedValueMock,
      apiEndpointMock
    );

    await handleAttach({ someFormData: 'formData' });

    expect(handleAttachMemoryToggleMock).toHaveBeenCalledTimes(1);
    expect(setLmdDataMock).not.toHaveBeenCalled();
    expect(setMemboxDataMock).not.toHaveBeenCalled();
  });
});