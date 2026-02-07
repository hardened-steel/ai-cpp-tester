#include <lib/box.hpp>


namespace lib {
    void BoxOfFruits::add(Fruit fruit)
    {
        fruits.insert(std::move(fruit));
    }

    std::size_t BoxOfFruits::count() const noexcept
    {
        return fruits.size();
    }
}
