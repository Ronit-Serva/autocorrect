#define main autocorrect_cli_main
#include "../src/autocorrect.cpp"
#undef main
#include <cassert>

int main() {
    using namespace ac;
    assert(distance("", "abc") == 3);
    assert(distance("planet", "plnaet") == 1);
    assert(distance("kitten", "sitting") == 3);
    assert(distance("abcd", "badc") == 2);
    // A bounded implementation must preserve OSA exactly within its radius,
    // including transpositions and values that cross a band edge.
    std::vector<string> small{""};
    for (int n = 1; n <= 5; ++n) for (int bits = 0; bits < (1 << n); ++bits) {
        string s(n, 'a');
        for (int i = 0; i < n; ++i) if (bits & (1 << i)) s[i] = 'b';
        small.push_back(s);
    }
    for (const auto& a : small) for (const auto& b : small)
        for (int radius = 0; radius <= 4; ++radius)
            assert(bounded_distance(a, b, radius) == std::min(distance(a, b), radius + 1));
    for (int n = 32; n <= 64; ++n) {
        string a(n, 'a'), b = a;
        for (int j = 0; j < n; j += 7) b[j] = 'b';
        for (int radius = 1; radius <= 6; ++radius)
            assert(bounded_distance(a, b, radius) == std::min(distance(a, b), radius + 1));
    }
    assert(weighted_distance("alphabet", "alfabet") < distance("alphabet", "alfabet"));
    assert(weighted_distance("garden", "garrden") < 1);
    assert(weighted_distance("can't", "cant") < 1);
    assert(phonetic("phone") == phonetic("fone"));
    assert(contextual_phonetic("school") == contextual_phonetic("skool"));
    assert(contextual_phonetic("action") == contextual_phonetic("akshun"));
    assert(contextual_phonetic("thumb") == contextual_phonetic("thum"));
    assert(contextual_phonetic("bad", true) != contextual_phonetic("pat", true));
    // Position-restricted silent-letter rules must not fire within a word.
    assert(weighted_distance("knit", "nit", .35, true, true) < .5);
    assert(weighted_distance("acknit", "acnit", .35, true, true) >= .5);
    assert(weighted_distance("lamb", "lam", .35, true, true) < .5);
    assert(weighted_distance("lambent", "lament", .35, true, true) >= .5);
    assert(weighted_distance("planet", "plnaet", .35) < weighted_distance("planet", "plnaet", .65));
    assert(phonetic(string(64, 'x')).size() <= MAX_WORD);
    assert(distance(phonetic(string(64, 'x')), phonetic(string(64, 'y'))) >= 0);
    assert(deletes("aaa", 2).size() == 3);
    // Exhaustively verify two-edit candidate retrieval on a small alphabet,
    // including edits around the seven-character index prefix boundary.
    std::vector<string> words;
    for (int n = 4; n <= 8; ++n) for (int bits = 0; bits < (1 << n); ++bits) {
        string s(n, 'a');
        for (int i = 0; i < n; ++i) if (bits & (1 << i)) s[i] = 'b';
        words.push_back(s);
    }
    std::vector<std::vector<uint64_t>> keys;
    for (const auto& w : words) keys.push_back(deletes(w.substr(0, PREFIX), 2));
    for (size_t i = 0; i < words.size(); ++i) for (size_t j = i; j < words.size(); ++j) {
        if (distance(words[i], words[j]) <= 2) {
            std::vector<uint64_t> intersection;
            std::set_intersection(keys[i].begin(), keys[i].end(), keys[j].begin(), keys[j].end(), std::back_inserter(intersection));
            assert(!intersection.empty());
        }
    }
    std::cout << "Unit checks passed\n";
}
