#ifndef CIRCULAR_QUEUE_H
#define CIRCULAR_QUEUE_H

#include <stdexcept>
#include <vector>

template <typename T>
class CircularQueue {
 private:
  std::vector<T> queue_;
  size_t front_ = 0;
  size_t rear_ = 0;
  size_t size_ = 0;
  size_t capacity_;

  class iterator {
   private:
    CircularQueue<T>* itr_queue_;
    size_t index_;
    size_t count_;

   public:
    iterator(CircularQueue<T>* queue, size_t index, size_t count);
    T& operator*() const;
    iterator& operator++();
    bool operator!=(const iterator& other) const;
  };

 public:
  explicit CircularQueue(size_t capacity);
  bool isEmpty() const;
  bool isFull() const;
  void enqueue(const T& element);
  T dequeue();
  size_t size() const;
  size_t capacity() const;
  iterator begin();
  iterator end();
};

#endif  // CIRCULAR_QUEUE_H