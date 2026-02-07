#pragma once
#include <lib/fruit.hpp>
#include <set>


namespace lib {
    // class container for fruits
    class BoxOfFruits
    {
        std::multiset<Fruit> fruits;

    public:
        BoxOfFruits() noexcept = default;
        void add(Fruit fruit);
        std::size_t count() const noexcept;
    };

    /**
        Given An empty box.
        When I place 2 x "apple" in it.
        Then The box contains 2 items.
    */
    using test_case_0 = void;
}
