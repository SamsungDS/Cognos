#include "circular_queue.h"

#include "nlohmann/json.hpp"

template <typename T>
CircularQueue<T>::CircularQueue(size_t capacity)
    : queue_(capacity), capacity_(capacity) {}

template <typename T>
bool CircularQueue<T>::isEmpty() const {
  return size_ == 0;
}

template <typename T>
bool CircularQueue<T>::isFull() const {
  return size_ == capacity_;
}

template <typename T>
void CircularQueue<T>::enqueue(const T& element) {
  if (isFull()) {
    front_ = (front_ + 1) % capacity_;
    size_--;
  }
  queue_[rear_] = element;
  rear_ = (rear_ + 1) % capacity_;
  size_++;
}

template <typename T>
T CircularQueue<T>::dequeue() {
  if (isEmpty()) {
    throw std::runtime_error("Queue is empty");
  }
  T element = std::move(queue_[front_]);
  front_ = (front_ + 1) % capacity_;
  size_--;
  return element;
}

template <typename T>
size_t CircularQueue<T>::size() const {
  return size_;
}

template <typename T>
size_t CircularQueue<T>::capacity() const {
  return capacity_;
}

template <typename T>
CircularQueue<T>::iterator::iterator(CircularQueue<T>* queue, size_t index,
                                     size_t count)
    : itr_queue_(queue), index_(index), count_(count) {}

template <typename T>
T& CircularQueue<T>::iterator::operator*() const {
  return itr_queue_
      ->queue_[(itr_queue_->front_ + index_) % itr_queue_->capacity_];
}

template <typename T>
typename CircularQueue<T>::iterator& CircularQueue<T>::iterator::operator++() {
  index_ = (index_ + 1) % itr_queue_->size();
  count_++;
  return *this;
}

template <typename T>
bool CircularQueue<T>::iterator::operator!=(const iterator& other) const {
  return count_ != other.count_;
}

template <typename T>
typename CircularQueue<T>::iterator CircularQueue<T>::begin() {
  return iterator(this, 0, 0);
}

template <typename T>
typename CircularQueue<T>::iterator CircularQueue<T>::end() {
  return iterator(this, 0, size_);
}

template class CircularQueue<nlohmann::json>;