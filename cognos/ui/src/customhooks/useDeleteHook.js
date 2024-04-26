const useDeleteHook = (setMemboxData, setShowFreeMemory, apiEndpoint) => {
  const handleDelete = async (item) => {
    setShowFreeMemory(false);

    try {
      const response = await fetch(`${apiEndpoint}/free_lmd`, {
        mode: 'cors',
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(item)
      });

      if (response.ok) {
        console.log("Successfully deleted LMD: ", item);
        const data = await response.json();
        setMemboxData(data);
      }
    } catch (error) {
      console.error("Error deleting LMD:", error);
    }
  };

  return { handleDelete };
};

export default useDeleteHook;
