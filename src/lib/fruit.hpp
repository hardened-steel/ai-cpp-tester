#pragma once
#include <string>
#include <string_view>


namespace lib {
    class Fruit
    {
        std::string kind;

    public:
        Fruit(std::string kind) noexcept
        : kind(std::move(kind))
        {}

        Fruit(const Fruit& other) = default;
        Fruit(Fruit&& other) noexcept = default;

        Fruit& operator = (const Fruit& other) = default;
        Fruit& operator = (Fruit&& other) noexcept = default;
        friend bool operator == (const Fruit& lhs, const Fruit& rhs) noexcept = default;
        friend auto operator <=> (const Fruit& lhs, const Fruit& rhs) noexcept = default;

        [[nodiscard]] std::string_view get_kind() const noexcept
        {
            return kind;
        }
    };
}
